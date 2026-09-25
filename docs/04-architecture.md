# 04 · 技术架构

## 1. 架构总览

```mermaid
flowchart TB
    subgraph FE["前端 · React 19 SPA (Vite + TS)"]
        F1[资讯台] --- F2[观点室] --- F3[写作台] --- F4[设置/提示词]
    end

    subgraph API["接口层 · FastAPI"]
        A1[REST /api/v1/*]
        A2[SSE /api/v1/stream]
        A3[Auth / 限流 / 配额]
    end

    subgraph DOMAIN["领域服务层"]
        D1[NewsService]
        D2[AnnotationService]
        D3[ReviewService]
        D4[ComposeService]
        D5[PromptService]
        D6[SyncService]
    end

    subgraph AGENT["Agent 层 · LangGraph + DeepAgents"]
        G1[ingest_graph]
        G2[review_graph]
        G3[compose_graph]
        SA[ScoutAgent]
        RA[ResearcherAgent]
        RVA[ReviewerAgent]
        WA[WriterAgent]
    end

    subgraph CONN["数据源接入层 · Connector 抽象"]
        C1[TushareConnector]
        C2[RssConnector 预留]
        C3[WeChatMPConnector 预留]
        C4[XueqiuConnector 预留]
    end

    subgraph INFRA["基础设施"]
        P[(PostgreSQL 16<br/>+ pgvector + pg_trgm)]
        R[(Redis 7)]
        S3[(对象存储 S3/MinIO)]
        LS[LangSmith]
    end

    FE --> API --> DOMAIN
    DOMAIN --> AGENT
    DOMAIN --> CONN
    D6 --> G1
    D3 --> G2
    D4 --> G3
    D3 -.检查结论.-> RA2[FactCard 缓存]
    AGENT --> P
    AGENT --> LS
    DOMAIN --> P
    DOMAIN --> R
    CONN --> S3
    G1 & G2 & G3 -- arq 任务 --> R
```

---

## 2. 分层职责

| 层 | 职责 | 不做什么 |
| --- | --- | --- |
| **接口层** | 鉴权、参数校验（Pydantic）、限流、SSE 推送、错误码 | 不写业务逻辑，不直接调 LLM |
| **领域服务层** | 业务编排、事务边界、状态机流转、权限校验、DTO 转换 | 不感知 LangGraph 细节，只通过 `AgentRuntime` 门面调用 |
| **Agent 层** | 三张图 + 四个子 Agent，封装所有 LLM 决策 | 不直接访问 HTTP 请求上下文；所有 IO 走工具/repository |
| **数据源接入层** | 与外部数据源通信，产出统一 `NewsItem` | 不写业务库表关系，不感知用户 |
| **基础设施** | PG / Redis / S3 / 可观测 | — |

> **重要边界**：Agent 层通过 `Repository` 协议访问数据库，而不是直接持有 ORM session。
> 这样便于单测（注入内存实现）与未来把 Agent 拆成独立服务。

---

## 3. 技术选型与理由

| 类别 | 选型 | 为什么 | 备选与何时换 |
| --- | --- | --- | --- |
| 包管理 | **uv** | 单文件锁、速度极快、原生 workspace | — |
| 运行时 | **Python 3.12** | `asyncio` 成熟、类型标注完善 | — |
| Web | **FastAPI** | async 原生 + Pydantic 集成 + OpenAPI 自动生成 | Litestar（团队更偏好时） |
| Agent 编排 | **LangGraph 1.x** | 唯一能同时表达**循环 + 并行 + 中断/恢复 + 持久化状态**的成熟方案；HITL 是一等公民 | 自研状态机（不必要，成本更高） |
| Agent 封装 | **deepagents** | 直接给到 planning / subagent / 虚拟 FS / skills 四个能力，避免重复造轮子 | 手写 middleware（当 deepagents 不满足时局部替换） |
| **LLM 档位** | **pro** `doubao-seed-2.1-pro`（1M，旗舰深度推理）／ **turbo** `doubao-seed-2.1-turbo`（256k，均衡主力，**默认档**）／ **lite** `doubao-seed-2.1-lite`（256k，轻量批量） | 三款**实测均为推理模型**（reasoning 占 97~100%）。同一分类任务：pro 194tok/6.5s、**turbo 36tok/2.1s**、lite 407tok/8.9s → **turbo 是甜点**；**lite 在简单任务上并不比 turbo 省**（"轻量"是能力定位，不是思考更少） | 私有化换自建 vLLM / Ollama 的 OpenAI 兼容端点（协议不变，零代码改动） |
| **Embedding** | `doubao-embedding-vision`（实测 2048 维） | 已定案；2048 > pgvector 索引上限 2000，暂走全表扫描 | 换模型需同步 `EMBEDDING_DIM` 并重建向量列 |
| 网页检索 | Tavily / 博查（国内） | **ResearcherAgent 必备**，tushare 覆盖不到海外与自由文本源 | 自建爬虫（量起来后） |
| 校验 | **Pydantic v2** | API schema 与 `with_structured_output` 复用同一套模型 | — |
| ORM | **SQLAlchemy 2.0 async** | 类型友好、支持 async、生态成熟 | SQLModel（会牺牲灵活性） |
| 迁移 | **Alembic** | 与 SQLAlchemy 同源；配 naming_convention 避免 autogenerate 噪声 | — |
| 主库 | **PostgreSQL 16** | 关系 + `vector` + `pg_trgm` + `jsonb` + 分区，一个库覆盖 90% 需求 | 向量量级 > 5000 万时拆出专用向量库 |
| 缓存/队列 | **Redis 7 + arq** | arq 是 asyncio 原生，与 FastAPI/LangGraph 同栈；比 Celery 轻 | 需要复杂路由/重试策略时换 Celery |
| 对象存储 | **S3 兼容** | 公告 PDF、导出稿、封面图 | — |
| 可观测 | **LangSmith + structlog** | LangGraph 原生溯源；业务日志与 trace 用 `run_id` 串联 | 私有化场景换 Langfuse（可自托管） |
| 前端 | **React 19 + Vite + TS** | 见 §8 | Next.js（需要 SSR/一体化时） |

### 3.1 为什么不直接用 LangChain Chain / 裸 OpenAI SDK

- **裸 SDK**：要实现并行检查、中断恢复、状态持久化，等于自己写一遍 LangGraph。
- **LCEL Chain**：线性管道无法表达"检查不通过 → 回到编辑 → 重新检查"的循环，也无法表达 HITL 断点。
- **LangGraph 的独有收益**：
  1. `interrupt()` + `Command(resume=)` → 大纲确认断点（本产品核心体验）
  2. Postgres checkpointer → 服务重启不丢进度（长文写作任务典型需要 60~120s）
  3. `Send` API → map-reduce 并行检查 N 条点评
  4. `astream_events` → 直接驱动前端 SSE 与"Agent 正在做什么"的可视化

---

## 4. 数据源接入层（抽象设计，本方案的关键工程点）

> **需求**：今天只用 tushare，明天要接 RSS / 公众号 / 雪球 / 交易所公告 / 板块行情，
> 且这些源的数据形态差异极大（结构化行情 vs 长篇文本 vs PDF 公告）。
> 因此抽象要覆盖两类：**资讯类（content）** 与 **市场数据类（market）**。

### 4.1 分层：ODS → DWD → 应用

```
外部源（快讯 / 长文 / 公告 / 政策 / 研报 …，以及将来的行情）
  ↓ Connector.fetch()          # 只负责"拿到原始数据"
raw_documents (ODS)            # 原始 payload 全量留档，jsonb，永不丢弃
  ↓ Normalizer.normalize()     # 转成渠道无关的统一信封 NormalizedItem
  ├─ 有 metrics ──▶ market_facts   # 数值事实（长表：一行一个指标）
  └─ 文本正文 ────▶ news_items     # 归一化、去重、打标、向量化，供业务查询
  ↓
应用层（素材 / 点评 / 体检 / 选题 / 写作）
```

**两条分流路径的判据只有一个**：`NormalizedItem.has_metrics`。
文本资讯与市场数值共用同一个中间层骨架，落库分支数因此固定为 2，
而不是"每加一种数据类型就加一条分支"。

**为什么保留 ODS？** 因为归一化规则会变（今天没抽出的字段明天想用）。
原始层留档 = 可以随时"重放"归一化，而不用重新调外部接口（省积分、抗断供）。
本次接快讯就吃到了这个红利：参数修正后，原始层里的历史 payload 可以直接重放。

### 4.2 核心协议

> **M2 修订（2026-09-20）**：中间层从 `NewsDraft` 泛化为 **`NormalizedItem`**。
> 原因：产品今天只有 tushare 快讯，明天要接 RSS / 公众号 / 雪球 / 交易所公告 / 板块行情，
> 这些源在**形状**上差异极大（长文本 vs 结构化行情）。用「统一信封 + 双扩展通道」吸收，
> 落库分支数固定为「有 metrics / 无 metrics」，而不是"每加一种数据类型就加一条分支"。
> `NewsDraft` 保留为别名（compat），等调用点迁完再删。

```python
# app/connectors/base.py
class SourceKind(str, enum.Enum):
    """条目的语义类别（比 content_type 粗一档），决定落库分流。"""
    news = "news"            # 快讯 / 长文
    announcement = "announcement"
    policy = "policy"
    research = "research"
    social = "social"
    market = "market"        # 行情 / 资金流等数值型


class Metric(BaseModel):
    """可核查的最小量化单元。将来"引用事实"与事实卡片都从这里取数，
    而不是去正文里正则撒网。"""
    name: str                       # 指标名，如"电池级碳酸锂均价"
    value: Decimal
    unit: str | None = None         # 万元/吨、%、亿元
    period: str | None = None       # 时点 / 区间标识，如 2026Q2
    ts_code: str | None = None      # 标的，标准码
    observed_at: datetime | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    """来源溯源：这一条到底从哪来（多源接入后排查问题的第一手信息）。"""
    connector_key: str | None = None
    api: str | None = None
    channel: str | None = None        # 渠道标识，如 tushare src=cls
    channel_label: str | None = None  # 渠道展示名，如"财联社"
    fetched_at: datetime | None = None


class NormalizedItem(BaseModel):
    """渠道无关的统一信封。★ title 可选 —— 数值型数据没有标题，
    落 DWD 时用 display_title 兜底（news_items.title 是 NOT NULL：
    正文摘要 → 指标名+数值 → external_id 逐级回退）。"""
    external_id: str
    kind: SourceKind = SourceKind.news
    content_type: ContentType       # 单一来源：app/models/enums.py（不再重复定义 Literal）
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    author: str | None = None
    url: str | None = None
    published_at: datetime          # 必须 tz-aware
    lang: str = "zh"
    source_name: str | None = None
    symbols: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    market_scope: list[str] = Field(default_factory=list)
    # ---- 两个扩展通道（新渠道靠它们吸收形状差异，而不是新增模型） ----
    attributes: dict[str, Any] = Field(default_factory=dict)   # 键值元信息（上游分类等）
    metrics: list[Metric] = Field(default_factory=list)        # 数值型事实
    provenance: Provenance = Field(default_factory=Provenance)
    extra: dict[str, Any] = Field(default_factory=dict)


NewsDraft = NormalizedItem   # 兼容别名（deprecated）


class RawItem(BaseModel):
    """原始条目：不做语义加工，只做必要的定位与幂等标识。"""
    external_id: str
    payload: dict[str, Any]            # 原始结构原样保留
    fetched_at: datetime
    source_ref: str | None = None
    content_type: ContentType = ContentType.flash
    channel: str | None = None         # ★ 来自哪个子渠道（一个实例覆盖多来源时必须逐条声明）


class ConfigField(BaseModel):
    """连接器配置项声明 —— 前端据此**动态渲染**表单，从此不认识任何具体连接器。"""
    key: str
    label: str
    type: Literal["text", "select", "multiselect", "number", "boolean"] = "text"
    options: list[dict[str, str]] = Field(default_factory=list)
    default: Any = None
    required: bool = False
    help: str | None = None


class ConnectorCapability(BaseModel):
    """连接器能力声明——调度器据此决定同步策略，前端据此渲染配置与展示。"""
    content_types: list[str]
    supports_incremental: bool = True
    supports_backfill: bool = True
    rate_limit_per_min: int | None = None
    requires_credentials: bool = False
    config_schema: list[ConfigField] = []   # 空 = 无需配置（既有连接器零改动）
    emits_metrics: bool = False             # 是否产出数值事实
```

#### 4.2.1 声明式字段映射（`ChannelSpec`）

**把「新增渠道 = 写代码」变成「新增渠道 = 写声明」。** 具体连接器不再手写 `normalize()`，
只声明"哪个字段从哪来"，由 `app/connectors/spec.py` 的通用实现执行。

```python
# app/connectors/spec.py
class FieldRef(BaseModel):
    """取值器：按序回退的候选路径 + 常量注入 + 默认值。"""
    candidates: list[str] = []      # FieldRef.of("title", "name")
    constant: Any = None            # FieldRef.const("财联社")
    default: Any = None


class ChannelSpec(BaseModel):
    key: str                        # 接口/渠道标识，进 provenance.api
    kind: SourceKind
    content_type: ContentType
    title / content / summary / author / url / source_name: FieldRef | None
    time: FieldRef | None
    time_formats: list[str]         # 该渠道的时间格式集合
    tz: str = "Asia/Shanghai"       # 上游时间无时区 → 显式补，避免按会话时区被隐式解释
    attributes / static_attributes: FieldRef / Any   # 键值扩展通道
    market_scope / industries: list[str]             # 静态标签
    symbol_fields / symbol_transform
    metric_specs: list[MetricSpec]  # 数值事实通道
    external_id_fields: list[str]   # 幂等键（稳定字段组合，不是全字段 hash）

    def normalize(self, payload, *, ctx, ...) -> NormalizedItem: ...
```

**取值器语法**：普通点分路径 `data.items.0.title`（支持嵌套 dict 与 list 下标）；
`$channel` / `$api` / `$fetched_at` 引用上下文 —— 上游返回里**没有**但语义必需的字段走这里注入
（tushare `news` 不返回 `src`，渠道身份只能这样注入，否则 9 个来源的 `source_name`
会全部退化成同一个兜底值）。

**为什么幂等键必须用稳定字段组合**：全字段 hash 会因为上游多回一个无关字段就产生新 id，
在原始层重复占位；而"渠道 + 时间 + 标题"跨次拉取稳定。

**纯函数约束**：`normalize()` 不碰 IO、**不读时钟**。条目时间从 `time` 字段解析，
失败退到 `ctx["fetched_at"]`（调用方从 RawItem 带进来，是数据不是环境），两者都没有则抛错 ——
不静默用 `now()`，否则回放不可复现。


class SyncCursor(BaseModel):
    """增量游标：每个连接器独立持久化，支持断点续拉。"""
    last_external_id: str | None = None
    last_published_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class DataSourceConnector(ABC):
    """所有数据源必须实现的契约。"""

    key: str                                  # 唯一标识，如 "tushare.flash"
    display_name: str
    capability: ConnectorCapability

    def __init__(self, config: dict[str, Any], credentials: dict[str, Any] | None = None) -> None:
        self.config = config
        self.credentials = credentials or {}

    @abstractmethod
    async def validate(self) -> tuple[bool, str]:
        """凭据/权限/连通性自检。返回 (是否可用, 人话说明)。"""

    @abstractmethod
    def fetch(self, cursor: SyncCursor, window: tuple[datetime, datetime]) -> AsyncIterator[RawItem]:
        """拉取原始数据流。必须支持分段，避免长区间一次性拉取。"""

    @abstractmethod
    def normalize(self, raw: RawItem) -> NormalizedItem:
        """原始 → 统一信封。必须是纯函数：不碰 IO、不读时钟。"""

    def empty_reason(self) -> str | None:
        """同步 0 条时的人话原因（各渠道判定依据不同，由连接器自己给）。
        同步编排只负责「问连接器」，不负责懂任何一个具体渠道。"""
        return None

    async def close(self) -> None:  # 可选钩子
        return None
```

### 4.3 注册表（插件式）

```python
# app/connectors/registry.py
_REGISTRY: dict[str, type[DataSourceConnector]] = {}   # 现行 key → 类
_ALIASES: dict[str, tuple[str, str]] = {}              # 历史 key → (现行 key, 人话说明)

def register(cls) -> type[DataSourceConnector]: ...
def alias(old_key: str, new_key: str, note: str = "") -> None: ...

def resolve_key(key: str) -> str: ...           # 历史 key → 现行 key
def migration_hint(key: str) -> dict | None: ...  # 供 API 出参给出迁移提示
def get_connector_class(key: str) -> type[DataSourceConnector]: ...
def available_connectors() -> list[dict]: ...    # 只列现行 key，不含别名
```

> 新增数据源 = 新增一个文件 + `@register` 装饰器，**不需要改调度器、不需要改 API、不需要改前端**
> （前端从 `GET /connectors/available` 的动态 `capability.config_schema` 渲染表单）。

#### 4.3.1 为什么注册表需要「别名」

`source_connectors.key` 是**持久化在数据库里**的。一旦某个连接器被拆分或改名，
历史行就会让 `get_connector_class()` 抛 `LookupError` ——
表现为"升级后同步在取连接器类的瞬间失败"，而不是给出可读提示。

M2 的实例：`tushare.news` 拆分成了 `tushare.flash`（快讯）+ `tushare.article`（长文/公告/政策/研报）。

```python
# app/connectors/tushare/__init__.py
alias("tushare.news", "tushare.article",
      note="该连接器已拆分：快讯请新建「Tushare 新闻快讯」（可选来源），"
           "本连接器继续负责长文 / 公告 / 政策 / 研报")
```

**别名指向 `article` 而不是 `flash`**：老行的配置是 `config.endpoints=[...]`（多接口），
指向 article 能**保留它原有的行为**；指向 flash 则因为缺少 `srcs` 配置会立刻变成"未配置来源"错误。

配套约定：
- `POST /connectors` 收到历史 key 时，**落库一律写现行 key**（别名只服务存量数据，不该继续进库）；
- `GET /connectors` 对存量老行返回 `key_migrated_to` + `migration_note`，前端展示提示但**不自动改数据**；
- 同步统计里带 `legacy_key`，日志打 `sync.legacy_key` 警告。

### 4.4 TushareConnector 实现要点

基于 tushare 的资讯类接口（详见 `tushare-data` skill 的接口清单）。

> **M2 拆分（2026-09-20）**：快讯从原来的"一个连接器覆盖 6 个接口"里独立出来。
> 一个连接器同时管快讯（按来源循环、小时粒度）与长文（按天粒度），
> 会让**配置项、权限探测、游标语义**三件事互相缠绕。现在拆成两个：

| 连接器 | 覆盖接口 | 特点 |
| --- | --- | --- |
| `tushare.flash` | `news`（doc 143） | 单实例可配**多个来源**（9 个 `src` 之一），按来源独立限流与游标；单次上限 1500 条 → 触顶自动二分细分 |
| `tushare.article` | `major_news` / `cctv_news` / `anns_d` / `npr` / `research_report` | 按接口粒度（天）拉取，接口权限逐个探测 |

| 接口 | 产出 content_type | 说明 |
| --- | --- | --- |
| `news` | `flash` | 主流财经网站快讯，6 年+ 历史，**`src` 为必选参数**（9 个来源） |
| `major_news` | `article` | 长篇通讯，8 年+ 历史 |
| `cctv_news` | `article` | 新闻联播文字稿（2017 起），适合宏观叙事素材 |
| `anns_d` | `announcement` | 全量公告，带 PDF url → 下载入对象存储 |
| `npr` | `policy` | 国家政策库：法规/条例/批复/通知原文 |
| `research_report` | `research_report` | 研报，用于观点参照与行业数据 |
| `irm_qa_sh` / `irm_qa_sz` | `interactive_qa` | 互动易问答，公司口径的原始表述（未接入） |

**字段映射全部走声明式 `ChannelSpec`**（`app/connectors/tushare/specs.py`），
连接器类里不再有手写的字段转换逻辑：

```python
# app/connectors/tushare/specs.py —— 新增 tushare 接口 = 在这里加一个 ChannelSpec
NEWS_SPEC = ChannelSpec(
    key="news",
    kind=SourceKind.news,
    content_type=ContentType.flash,
    title=FieldRef.of("title"),
    content=FieldRef.of("content", "text"),
    # ★ 渠道名由连接器注入：上游返回里没有 src，写 p.get("src") 只会永远落到兜底值
    source_name=FieldRef.of("$channel_label"),
    time=FieldRef.of("datetime", "pub_time", "time"),
    time_formats=["%Y-%m-%d %H:%M:%S", "%Y%m%d %H%M%S"],
    attributes={"channels": FieldRef.of("channels")},
    static_attributes={"upstream_api": "news"},
    market_scope=["a_share"],
    # 幂等键 = 渠道 + 发布时间 + 标题
    external_id_fields=["$channel", "datetime", "title"],
)

# 长文/公告/政策/研报的字段名**未逐一真机验证**（多数接口无权限），
# 因此一律用多候选回退声明：取到哪个算哪个。上游改字段名只需在这里加一个候选。
ARTICLE_SPECS = {"major_news": ..., "cctv_news": ..., "anns_d": ..., "npr": ..., "research_report": ...}
```

```python
# app/connectors/tushare/flash.py（骨架）
@register
class TushareFlashConnector(TushareBase):
    key = "tushare.flash"
    display_name = "Tushare 新闻快讯"
    capability = ConnectorCapability(
        content_types=["flash"],
        rate_limit_per_min=200,
        requires_credentials=True,
        config_schema=[ConfigField(key="srcs", label="新闻来源", type="multiselect",
                                   options=[...9 个来源...], required=True,
                                   default=["cls", "sina"])],
    )

    async def _query_flash(self, src, start, end) -> list[dict]:
        # ★ src 必传 + 时间用 %Y-%m-%d %H:%M:%S —— 旧实现这两点都错，导致"返回 0 行"
        return await self._query("news", channel=src, src=src,
                                 start_date=start.strftime(TUSHARE_DATETIME_FMT),
                                 end_date=end.strftime(TUSHARE_DATETIME_FMT))

    async def fetch(self, cursor, window) -> AsyncIterator[RawItem]:
        # - 逐来源循环；每个来源用自己的游标（cursor.payload["srcs"][src]）
        # - 每小时一段；某段返回 1500 条（触顶）则二分细分，深度上限 4 层
        # - 某段失败：记入 failed_segments 且**不推进该来源游标** → 下次重来
        # - tushare SDK 是同步的：一律 asyncio.to_thread（单进程单事件循环，阻塞即全站卡住）
        ...

    def normalize(self, raw: RawItem) -> NormalizedItem:
        # 纯函数：映射逻辑全在 NEWS_SPEC，这里只补来源溯源
        ...
```

#### 4.4.1 Spike #1 实测结论

用当前 token 真机跑全部资讯接口。

**M2 更正（2026-09-20，实测已验证）**：`news` 的"返回 0 行"**是我们的参数写错，不是权限问题**。
旧实现有两个错误，两个都会让接口返回空：

| 错误 | 旧实现 | 官方规格 | 后果 |
| --- | --- | --- | --- |
| 没传 `src` | `src` 默认不传 | **必选**，9 个来源之一 | 返回空 |
| 时间格式错 | `%Y%m%d %H%M%S` | `%Y-%m-%d %H:%M:%S` | 返回空 |

修正后真机结果（3 天窗口，来源 `cls` + `sina`）：

```
[validate] Tushare 快讯连接正常，近 3 小时有数据的来源：财联社, 新浪财经
[sync]  fetched 3842 / inserted 3799 / duplicated 43 / failed_segments []
[flash sources] {'财联社', '新浪财经'}
```

再配上第三个来源 `10jqka` 亦探测有数据（财联社 / 新浪财经 / 同花顺）。

**这次踩坑留下三条必须记住的教训**：

1. **"返回 0 行"和"无权限"是两种完全不同的故障**，绝不能混为一谈。
   `probe_srcs()` / `probe_endpoints()` 必须把它们分开：抛异常 = 无权限，
   返回 0 行 = 区间为空（**也可能是我们参数写错了**，文案要把两种可能都写出来，不替用户下结论）。
2. **上游返回里没有的字段不能靠读 payload 拿**。`news` 不返回 `src`，
   所以 `p.get("src")` 永远拿到 None —— 渠道身份必须由连接器注入（`$channel` / `$channel_label`）。
   旧实现就是这样把 9 个来源的 `source_name` 全部退化成同一个兜底值。
3. **pandas 的脏值会一路炸到数据库**。tushare SDK 走 pandas，缺失字段是 `float('nan')`，
   `json.dumps` 输出裸 `NaN`（非法 JSON），PostgreSQL jsonb 直接拒收：

   ```
   invalid input syntax for type json: Token "NaN" is invalid
   ```

   快讯里"没有标题"的行很常见，所以这是必然会撞的。
   修法是在**数据入口**统一归一（`app/lib/hash.py::json_safe`），
   并让 `canonical_json` 也走它，保证"入库形态"与"参与 hash 的形态"一致。
   注意 `pd.NaT` 是 `datetime` 的子类，必须先判类型名再判 `isoformat()`，
   否则会被转成看着很正常的字符串 `"NaT"`（脏数据伪装成有效值）。

全部接口的权限现状：

| 接口 | 实测 | 说明 |
| --- | --- | --- |
| `news`（快讯） | ✅ **可用**（参数修正后） | 需 `src`；单次上限 1500 条；返回无 id / 无 src / 无 url |
| `major_news` | ✅ 可用（800 条/天量级） | 长篇通讯，字段 `title / pub_time / src / url` |
| `cctv_news` | ✅ 可用（14 条/天） | 参数是 `date=YYYYMMDD`，**不是** start_date/end_date |
| `anns_d` | ❌ 无权限 | 明确抛"没有接口访问权限" |
| `npr` | ❌ 无权限 | 同上 |
| `research_report` | ❌ 无权限 | 同上 |
| `trade_cal` / `daily` | ✅ 可用 | 行情类不受限 |

**由此确定的四条工程规则（已落在代码里）**：

1. **`validate()` 必须逐个探测来源/接口**，而不是等主查询失败 ——
   结果写入 `source_connectors.config.probe`，UI 逐项渲染"哪个来源有数据、哪个无权限/为空"，
   而不是笼统地报一句"接口无权限"。
2. **只跑已探测可用的来源/接口**，不在无权限的接口上浪费积分。
3. **同步结果为空必须给出原因** —— `DataSourceConnector.empty_reason()` 由**连接器自己实现**
   （判定依据因渠道而异），同步编排只负责问，不负责懂 tushare。
4. **单次上限（1500）触顶时必须细分窗口**，不能当作正常结果 —— 否则静默丢数据。

> 影响：公告 / 政策 / 研报三类素材需要更高积分的 token 或改用其他数据源（RSS / 交易所）。
> 这正是"数据源可插拔"存在的意义 —— 但**插拔的前提是先把参数写对**，
> 否则会把"我们的 bug"误判成"对方没权限"，白白绕开一个本来可用的数据源。

### 4.5 同步调度

```python
# app/services/sync_service.py（骨架）
async def run_sync(connector_id: UUID) -> None:
    run = await sync_repo.start_run(connector_id)          # sync_runs: running
    success = failed = duplicated = 0
    try:
        async with connector_factory(connector_id) as conn:
            async for raw in conn.fetch(cursor, window):
                row_id = await raw_repo.upsert(raw)         # ODS，幂等（canonical JSON hash）
                draft = conn.normalize(raw)
                # ★ 返回 (news_id, is_new)：命中 content_hash 时 is_new=False，
                #   但绝不能丢弃 —— 必须追加 source_refs + duplicate 关联 + 簇 source_count，
                #   否则"多源交叉验证"退化为单源（见 05-database-schema.md §4.9）
                news_id, is_new = await news_repo.upsert_draft(draft, row_id)
                if is_new:
                    await enrich_queue.enqueue(news_id)      # 异步打标/向量化
                    success += 1
                else:
                    await news_repo.link_duplicate(news_id, row_id)   # 跨源登记来源
                    duplicated += 1
                # ★ 落库分流：带数值事实的条目额外写一张表（文本与数值分表存储）。
                #   放在编排层而不是各连接器里 —— 渠道不该关心存储长什么样，
                #   将来接行情源时这段完全不用改。
                if draft.has_metrics:
                    facts_written += await fact_repo.upsert_from_item(
                        draft, connector_id, raw_document_id=row_id, news_item_id=news_id)
                await sync_repo.touch_cursor(connector_id, raw)  # 每段更新，支持续拉
    except Exception as exc:
        await sync_repo.fail_run(run.id, exc)
        log.exception("sync failed", connector_id=connector_id)
        raise
    finally:
        await sync_repo.finish_run(run.id, success, failed, duplicated=duplicated)
        # ★ 空结果必须给出原因，否则用户以为"同步成功但没数据"是系统坏了。
        #   判定依据因渠道而异 → 问连接器自己，编排层不认识任何具体渠道。
        if run.fetched_count == 0:
            stats["empty_reason"] = empty_reason(connector)
        stats["facts_written"] = facts_written
        await interest_service.recall_for_users(since=...)     # 兴趣召回
```

**错峰与限流**：同一 connector 不允许并发运行（Redis 分布式锁）；
全局并发上限由配置控制；非交易日自动降频。

**多来源连接器的游标**：`SyncCursor.payload` 是自由字段，快讯把**按来源分组的独立进度**
存在 `payload["srcs"][src]` 里，零迁移成本；同时保证"某个来源失败不拖累其他来源"。

---

## 5. Agent 编排设计

### 5.1 三张图

| 图 | 触发 | 关键特性 |
| --- | --- | --- |
| `ingest_graph` | 同步任务 / 手动重放 | 打标、实体抽取、聚类、重要度打分；批处理，无 HITL |
| `review_graph` | 用户提交检查 | **`Send` API 并行 map-reduce**；每条点评三轨并行 |
| `compose_graph` | 用户触发写作 | **`interrupt()` HITL 断点**；DeepAgent 嵌套；流式输出 |

### 5.2 `review_graph` 骨架

```python
# app/agents/review/graph.py
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, interrupt, Command
from typing import Annotated, TypedDict
import operator


class ReviewState(TypedDict):
    project_id: str
    annotation_ids: list[str]
    annotation_versions: dict[str, str]         # annotation_id -> version_id
    fact_cards: Annotated[dict[str, dict], operator.or_]
    findings: Annotated[list[dict], operator.add]
    report_ids: list[str]
    summary: str


def fan_out_annotations(state: ReviewState):
    """map：为每条点评派生一个子任务（并行）。"""
    return [Send("review_one", {**state, "current_annotation_id": aid})
            for aid in state["annotation_ids"]]


async def review_one(state: dict):
    """单条点评的三轨检查并行执行。

    ★ FactCard 不再在 review 时同步生成：资讯级事实基线由 ingest 阶段异步预生成，
      这里直接读缓存（未命中才降级为实时检索并打标 trigger_source='on_demand'）。
      这是"检查单条 < 8s"能达成的前提，也是最大的一项成本优化。
    """
    aid = state["current_annotation_id"]
    version = state["annotation_versions"][aid]
    news_id = state["news_item_of"][aid]

    fact_card = await fact_card_repo.get_by_news(news_id)          # 缓存优先
    if fact_card is None:
        fact_card = await research_agent.arun(news_item_id=news_id, trigger="on_demand")

    async with asyncio.TaskGroup() as tg:
        t_fact = tg.create_task(review_agent.fact_track(version, fact_card))
        t_logic = tg.create_task(review_agent.logic_track(version, fact_card))
        t_comp = tg.create_task(review_agent.compliance_track(version))
    findings = t_fact.result() + t_logic.result() + t_comp.result()

    return {"findings": findings, "fact_cards": {aid: fact_card.model_dump()}}


async def reduce_and_persist(state: ReviewState):
    report = aggregate(state)                     # severity 排序 + verdict 判定
    await report_repo.save_many(report)           # review_reports + review_findings
    return {"report_ids": report.ids, "summary": report.summary}


builder = StateGraph(ReviewState)
builder.add_node("prepare", prepare_context)
builder.add_conditional_edges("prepare", fan_out_annotations, ["review_one"])
builder.add_node("review_one", review_one)
builder.add_edge("review_one", "reduce_and_persist")
builder.add_node("reduce_and_persist", reduce_and_persist)
builder.add_edge("reduce_and_persist", END)

review_graph = builder.compile(
    checkpointer=postgres_checkpointer,           # 可恢复、可重放
    store=postgres_store,                         # 跨 run 的长期记忆（观点库/风格）
)
```

**结构化输出**用 Pydantic + `with_structured_output`，避免解析自由文本：

```python
class FindingList(BaseModel):
    findings: list[Finding]

structured = model.with_structured_output(FindingList)
```

### 5.3 `compose_graph` 骨架（WriterAgent = DeepAgent）

```python
# app/agents/compose/graph.py
class ComposeState(TypedDict):
    project_id: str
    brief: str
    fact_cards: list[dict]
    prompt_bundle: dict                      # 从 PromptService 编译出的技能包
    outline: str | None
    sections: Annotated[dict[str, str], operator.or_]
    final_md: str | None
    citation_map: dict[str, list[str]]
    todos: list[str]
    # ★ 用户在写作中途注入的指令（"第二段压缩一半"）。DeepAgent 每次 ainvoke 是无状态的，
    #   必须把累积的 messages 显式传进去，否则中途指令根本进不了子 agent。
    messages: Annotated[list[dict], operator.add]


async def build_brief(state):  # 装载素材 → 虚拟文件系统
    fs = StateBackend(state)
    fs.write("/brief.md", render_brief(state))
    for fc in state["fact_cards"]:
        fs.write(f"/facts/{fc['news_item_id']}.md", render_fact_card(fc))
    fs.write("/style-guide.md", state["prompt_bundle"]["style"])
    fs.write("/forbidden.md", state["prompt_bundle"].get("forbidden", ""))
    return {"brief": fs.read("/brief.md")}


async def plan_and_outline(state):
    agent = build_writer_agent(            # ← deepagents: create_deep_agent
        model=strong_model,
        tools=[...],
        system_prompt=writer_system_prompt(state["prompt_bundle"]),
        subagents=[outline_agent, section_agent, fact_check_agent, style_agent, title_agent],
        backend=StateBackend(state),       # 虚拟 FS
        skills=[state["prompt_bundle"]["skill"]],   # 用户提示词 → Skill
    )
    result = await agent.ainvoke({"messages": [{"role": "user", "content": OUTLINE_TASK}]})
    return {"outline": extract_outline(result)}


async def hitl_outline(state):
    """HITL 断点：等待用户确认大纲。"""
    decision = interrupt({
        "type": "outline_approval",
        "outline_md": state["outline"],
        "options": ["approve", "edit", "regenerate"],
    })
    if decision["action"] == "approve":
        return {"outline": state["outline"]}
    if decision["action"] == "edit":
        return {"outline": decision["outline_md"]}
    return {"outline": state["outline"]}    # regenerate → 路由回 plan_and_outline


async def write_sections(state):
    """分段并行写作 → 事实复核 → 风格统一（DeepAgent 内部通过 subagent 完成）。

    ★ 必须把 state["messages"]（用户中途指令）显式塞进 ainvoke 的输入，
      否则 `update_state` 注入的指令进不了 DeepAgent 内部。
    """
    agent = build_writer_agent(...)
    result = await agent.ainvoke({
        "messages": [
            {"role": "user", "content": SECTION_TASK},
            *state.get("messages", []),          # ← 中途指令累积
        ]
    })
    return {"sections": extract_sections(result)}


builder = StateGraph(ComposeState)
builder.add_node("build_brief", build_brief)
builder.add_node("plan_and_outline", plan_and_outline)
builder.add_node("hitl_outline", hitl_outline)
builder.add_node("write_sections", write_sections)
builder.add_node("persist", persist_article)
builder.add_edge(START, "build_brief")
builder.add_edge("build_brief", "plan_and_outline")
builder.add_edge("plan_and_outline", "hitl_outline")
builder.add_conditional_edges("hitl_outline", route_after_approval, {
    "write": "write_sections", "replan": "plan_and_outline", "edit": "plan_and_outline",
})
builder.add_edge("write_sections", "persist")
builder.add_edge("persist", END)

compose_graph = builder.compile(checkpointer=postgres_checkpointer, store=postgres_store)
```

**恢复与续跑**：

```python
# 用户确认大纲
await compose_graph.aupdate_state(config, Command(resume={"action": "approve"}))
# 写作中途发指令
await compose_graph.aupdate_state(config, {"messages": [{"role": "user", "content": "第二段压缩一半"}]})
```

### 5.4 arq worker 与 HITL 长任务的生命周期（重要修订）

**问题**：`compose_graph` 在 `hitl_outline` 节点 `interrupt()` 后进入 `waiting_human`。
如果这个 arq job 一直挂着等待用户确认，20 个并发用户就能耗尽全部 worker 槽位；
且 arq 的 job timeout 会把等待中的任务判为超时。

**规则**：**interrupt = job 结束，resume = 新 job**。

| 阶段 | 动作 |
| --- | --- |
| 触发写作 | `POST /projects/{id}/compose` → enqueue `compose_job` → `202 {run_id}` |
| 跑到 `interrupt` | job **正常结束**；落 `agent_runs.status='waiting_human'` + `interrupt_payload`；推 SSE `compose.outline_ready` |
| 用户确认 | `POST /runs/{id}/resume` → enqueue **新 job** `compose_resume_job` → 调 `Command(resume=...)` 续跑 |
| 服务重启 | Postgres checkpointer 恢复；`waiting_human` 的 run 由启动时的扫描任务重新入队 |

```python
# app/workers/settings.py
class WorkerSettings:
    max_jobs = 8                       # 低并发高耗时：LLM 调用是 IO 密集，但单 job 占用久
    job_timeout = 900                  # 15min，单次"无中断连续执行"的上限
    max_tries = 2                      # LLM 任务不做自动重试（成本 + 非幂等），失败交用户决定
    poll_delay = 0.5
    health_check_interval = 30
    # 关键：compose_job 必须在 interrupt 时 return，而不是 await 用户输入
```

**僵尸 run 清理**：定时任务扫描 `status='waiting_human' AND updated_at < now() - interval '24 hours'`
→ 置 `cancelled` 并通知用户。否则中断的 run 会永久堆积。

### 5.5 两个 `store` 的用途（长期记忆）

| 存储 | 内容 | 用途 |
| --- | --- | --- |
| `checkpointer` | 单次 run 的完整状态 | 断点续跑、失败恢复 |
| `store` | 跨 run 的长期记忆 | 观点库（历史观点向量）、风格画像、用户偏好、finding 驳回历史 |

> `store` 是 M4 "越用越懂你" 的技术基础：`uniqueness` 轨道查历史观点，
> `WriterAgent` 从 store 取 few-shot 用户历史成稿，风格克隆效果随时间变好。

---

### 5.6 模型档位路由（场景 → 档位）

路由表在 `app/services/model_provider.py` 的 `DEFAULT_TIER`，可用 `LLM_TIER_OVERRIDES`
按场景覆盖，无需改代码。

| 场景（Task） | 档位 | 依据 |
| --- | --- | --- |
| `classify` 打标 / 分类 / 聚类 | **turbo** | 简单高频；turbo 实测 36tok/2.1s，全场最省 |
| `extract` 实体 / 关键词抽取 | **turbo** | 同上 |
| `title` 标题 / 摘要候选 | **turbo** | 量中等，需要一点质量 |
| `summarize` 摘要 | **lite** | 批量、高吞吐 |
| `fact_check` 事实复核（对照 FactCard） | **lite** | 对照型任务，不需要长链推理 |
| `review` 三轨检查 | **turbo** | 需要推理质量；pro 太慢（核查 108s），lite 复杂推理弱 |
| `write_section` 段落写作 | **turbo** | 局部任务量大，turbo 全能力且价约 pro 一半 |
| `style` 风格统一 | **turbo** | 同上 |
| `write_plan` 大纲规划 | **pro** | **唯一**值得用 pro 的场景：决定全文结构，需要长链推理 |

> **★ 延迟红线（实测）**：核查类任务单次 **48~108 秒**（pro 108s / turbo 56s / lite 48s），
> 远超 `docs/01` §6 的「检查单条 < 8s」。由此确定两条硬规则：
> 1. **默认检查路径必须保留规则版**（`rules-v1`），LLM 检查作为可选的"深度检查"；
> 2. 凡是走 LLM 的检查 / 写作，**必须异步**（arq + SSE 进度），不能在请求里同步等待。

---

## 6. 提示词体系：从「文本框」到「技能包」

> 用户说"用户可以单独配置自己的提示词管理"。**不要只做一个 CRUD 文本框列表**，
> 那会让用户产出质量参差、也无法被 Agent 有效使用。设计成**可编译的技能包**。

### 6.1 提示词分类（`prompt_kind`）

| 类型 | 作用 | 示例 |
| --- | --- | --- |
| `persona` | 人格设定 | "我是 10 年买方研究员，说话直接，喜欢用反问" |
| `style` | 文风与句式 | "短句为主，每段不超 4 行，少用形容词，数据必须带口径" |
| `structure` | 文章结构模板 | "开头钩子 → 事实复述 → 我的判断 → 反面情形 → 结论" |
| `forbidden` | 禁忌清单 | "禁用'赋能/闭环/抓手'；不写收益预测；不提具体仓位" |
| `research` | 事实检索偏好 | "优先看年报原文，其次看券商研报，自媒体仅作线索" |
| `custom` | 自由文本 | 用户自定义任何补充要求 |

### 6.2 编译流程

```
用户编辑提示词（Markdown + 变量 {{market}} {{target_reader}}）
    → 保存为 prompt_template + prompt_template_version（不可变快照）
    → 选题写作时选择一组模板 → PromptCompiler 编译
         ├─ 拼成 system_prompt 段落
         ├─ 生成 Skill 包（SKILL.md + 约束清单 + few-shot 示例）
         └─ 变量注入校验（缺失变量 → 提交前拦截）
    → 注入 WriterAgent
```

**Why Skill 而不是塞进 prompt**：`deepagents` 的 skills 是**渐进式加载**的 ——
只有相关时才加载全文，能显著降低长文写作时的上下文占用，
且用户可以在不重启服务的情况下更新自己的风格包。

### 6.3 官方模板库

提供 6~8 套开箱即用的模板（"雪球短评体"、"公众号深度复盘"、"政策解读"、
"财报拆解"、"行业周报"、"快讯点评"），新用户直接选，降低冷启动成本。

---

## 7. API 设计

### 7.1 约定

- 前缀 `/api/v1`，JWT 鉴权，`X-Request-Id` 贯穿日志与 trace
- 分页：`?cursor=&limit=`（游标式，适配时间流）
- 错误：`{"code": "REVIEW_BLOCKED", "message": "...", "details": {...}}`
- 长任务：返回 `202 + {run_id}`，进度走 SSE

### 7.2 核心端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| **数据源** | | |
| `GET` | `/connectors/available` | 可用连接器 + 能力声明（`config_schema` 供前端动态渲染配置表单） |
| `PATCH` | `/connectors/{id}` | 改配置 / 改名 / 改计划（前端提交完整 `config` 对象） |
| `GET` | `/market/facts` | 数值事实读取（按标的 / 指标 / 时间区间；本期用于验证落库路径） |
| `GET` `POST` `PATCH` `DELETE` | `/connectors` | 连接器实例 CRUD |
| `POST` | `/connectors/{id}/validate` | 凭据与权限自检 |
| `POST` | `/connectors/{id}/sync` | 手动触发同步（可指定时间窗回填） |
| `GET` | `/connectors/{id}/runs` | 同步历史与统计 |
| **资讯** | | |
| `GET` | `/news` | 资讯流（筛选：时间/类型/市场/行业/来源/重要度/已读） |
| `GET` | `/news/{id}` | 详情（含聚类内其他来源、关联标的、相关历史） |
| `GET` | `/news/clusters/{id}` | 事件簇展开 |
| `POST` | `/news/{id}/actions` | 收藏/隐藏/评级/已读 |
| `GET` | `/news/inbox` | 兴趣召回的个人化收件箱 |
| `POST` | `/news/search` | 语义 + 关键词混合检索 |
| **点评** | | |
| `POST` | `/annotations` | 创建点评（批量，`items[]`） |
| `GET` | `/annotations` | 列表（按项目/资讯/状态过滤） |
| `PATCH` | `/annotations/{id}` | 更新（生成新版本） |
| `GET` | `/annotations/{id}/versions` | 版本历史 |
| `POST` | `/annotations/{id}/restore` | 回退到某版本 |
| **检查** | | |
| `POST` | `/reviews` | 提交检查（批量）→ `202 {run_id}` |
| `GET` | `/reviews/{id}` | 报告详情 |
| `GET` | `/reviews/by-project/{pid}` | 项目级汇总 |
| `PATCH` | `/reviews/findings/{fid}` | 采纳 / 驳回（带理由）/ 标记已确认 |
| `POST` | `/reviews/{id}/recheck` | 增量复检 |
| `GET` | `/fact-cards/{news_item_id}` | 事实卡片 |
| **提示词** | | |
| `GET` `POST` | `/prompt-templates` | 列表（含官方库）/ 创建 |
| `PATCH` `DELETE` | `/prompt-templates/{id}` | 更新 / 删除 |
| `GET` | `/prompt-templates/{id}/versions` | 版本历史 |
| `POST` | `/prompt-templates/{id}/test` | 用样例文本试写一段，预览效果 |
| **选题与写作** | | |
| `POST` | `/projects` | 创建选题 |
| `GET` `PATCH` | `/projects/{id}` | 详情 / 更新（素材、提示词、要求） |
| `POST` | `/projects/{id}/compose` | 触发写作 → `202 {run_id}` |
| `POST` | `/runs/{run_id}/resume` | HITL 恢复（大纲确认 / 中途指令） |
| `POST` | `/runs/{run_id}/cancel` | 取消 |
| `GET` | `/runs/{run_id}` | 状态、步骤、token 消耗、trace 链接 |
| **稿件** | | |
| `GET` `PATCH` | `/articles/{id}` | 详情 / 人工编辑（生成新版本） |
| `GET` | `/articles/{id}/versions` | 版本列表 |
| `GET` | `/articles/{id}/diff` | 两版本 diff |
| `POST` | `/articles/{id}/regenerate-section` | 段落重写 |
| `GET` | `/articles/{id}/traceability` | 段落 → 点评 → 资讯 → 证据链路 |
| `POST` | `/articles/{id}/export` | 导出 MD / HTML / DOCX |
| **实时** | | |
| `GET` | `/stream/runs/{run_id}` | SSE 事件流 |
| **系统** | | |
| `GET` | `/me/usage` | 用量与配额 |
| `GET` | `/me/interests` `PUT` | 兴趣画像 |

---

## 8. 前端方案

### 8.1 决策：React SPA，不用 Astro 做主体

| 维度 | Astro | React SPA (Vite) | 结论 |
| --- | --- | --- | --- |
| 页面性质 | 内容/静态优先 | **登录后强交互后台** | React |
| SEO | 强 | 无（不需要） | React 不吃亏 |
| 交互复杂度 | 岛屿间状态共享麻烦 | 天然全局状态 | React |
| 实时流（SSE 流式写作） | 需要 client component 包裹 | 直接处理 | React |
| 富文本编辑器 | 需 client:only | 直接 | React |
| 构建/心智 | 多一层 island 规则 | 简单 | React |
| 首屏 | 更快 | 需 code split | 差异不大（后台应用可接受） |
| 局限 | — | 落地页/文档站不擅长 | 用 Astro 单独做 marketing site |

**最终**：主应用 **React 19 + Vite + TypeScript**；未来若需要官网/文档/公开内容站，再单独建一个 Astro 项目（`apps/site`），不混在主应用里。

### 8.2 前端技术栈

| 类别 | 选型 | 用途 |
| --- | --- | --- |
| 框架 | React 19 + Vite 6 + TS 5.x | SPA |
| 路由 | TanStack Router | 类型安全路由 |
| 数据 | TanStack Query v5 | 服务端状态、缓存、乐观更新 |
| 客户端状态 | Zustand | 选中态、编辑器草稿、UI 偏好 |
| 样式 | Tailwind CSS v4 | 原子化 |
| 组件 | shadcn/ui + Radix | 可复制可改的无样式组件 |
| 表单 | react-hook-form + zod | 校验与复用后端 schema 思路 |
| 富文本 | **Tiptap** | 点评编辑器 + 文章编辑器 |
| 虚拟列表 | TanStack Virtual | 资讯流万级条目流畅滚动 |
| 图表 | ECharts | 行情小图、用量看板 |
| 流式 | 原生 `EventSource`（+ fetch SSE 兜底） | 写作与检查进度 |
| diff | `diff-match-patch` / `react-diff-viewer` | 版本对比 |
| 测试 | Vitest + Playwright | 单测 + E2E |

### 8.3 页面结构

```
/                        今日收件箱（兴趣召回 + 重要资讯）
/news                    资讯流（筛选 + 批量选择）
/news/:id                资讯详情（抽屉或整页）
/inbox/review            观点室：批量点评工作台（左写 / 右原文）
/inbox/review/:id        单条点评 + 体检报告
/projects                选题列表
/projects/:id            选题详情（素材 / 提示词 / 写作要求）
/projects/:id/compose    写作台（大纲 → 流式成稿 → 编辑 → 导出）
/articles                稿件库
/articles/:id            稿件详情（编辑 / 版本 / 可追溯）
/settings/connectors     数据源管理
/settings/interests      兴趣画像
/settings/prompts        提示词管理
/settings/style          风格画像（从历史文章提取）
/usage                   用量与成本
```

### 8.4 前端工程要点

- **SSE 断线重连**：带 `Last-Event-ID`，服务端补发丢失事件
- **乐观更新**：评级/收藏即时反馈，失败回滚 + Toast
- **草稿本地兜底**：点评内容同时写 `localStorage`，网络异常不丢字
- **键盘优先**：资讯流与点评工作台全键盘可操作（重度用户效率）
- **长列表性能**：虚拟滚动 + 分页游标
- **错误边界**：Agent 任务失败要显示"哪一步失败 + 可重试"，不要白屏

---

## 9. 目录结构

```
news-director-agent/
├── apps/
│   ├── api/                          # FastAPI 后端
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── core/                 # 配置、日志、安全、依赖注入
│   │   │   ├── api/v1/               # 路由（thin controllers）
│   │   │   ├── domain/               # 领域模型（纯 Pydantic / dataclass）
│   │   │   ├── services/             # 领域服务（事务边界）
│   │   │   ├── repositories/         # 数据访问（Protocol + SQLAlchemy 实现）
│   │   │   ├── connectors/           # ★ 数据源接入层
│   │   │   │   ├── base.py           #   契约：RawItem / NormalizedItem(=NewsDraft) / Metric / Provenance
│   │   │   │   ├── spec.py           #   ★ ChannelSpec 声明式字段映射（新增渠道 = 写声明）
│   │   │   │   ├── registry.py       #   插件注册 + 历史 key 别名
│   │   │   │   └── tushare/
│   │   │   │       ├── base.py       #   凭据 / 同步 SDK 调用（to_thread）/ 按渠道独立限流
│   │   │   │       ├── specs.py      #   6 个 tushare 接口的 ChannelSpec 声明
│   │   │   │       ├── flash.py      #   tushare.flash：快讯（多来源、1500 条触顶细分）
│   │   │   │       └── connector.py  #   tushare.article：长文 / 公告 / 政策 / 研报
│   │   │   ├── agents/               # ★ Agent 层
│   │   │   │   ├── runtime.py        #   AgentRuntime 门面
│   │   │   │   ├── ingest/           #   ScoutAgent + ingest_graph
│   │   │   │   ├── research/         #   ResearcherAgent + 4 个子代理
│   │   │   │   ├── review/           #   ReviewerAgent 三轨 + review_graph
│   │   │   │   ├── compose/          #   WriterAgent + compose_graph
│   │   │   │   ├── prompts/          #   系统提示词模板
│   │   │   │   └── skills/           #   Skill 定义与编译
│   │   │   ├── models/               # SQLAlchemy 模型（含 market.py：数值事实表）
│   │   │   ├── schemas/              # API Pydantic schema
│   │   │   ├── workers/              # arq 任务（sync / review / compose / enrich）
│   │   │   └── lib/                  # 去重、向量、文本、限流工具
│   │   │                             #   含 hash.py::json_safe（pandas 脏值归一）
│   │   ├── alembic/
│   │   │   └── versions/
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── .env.example
│   └── web/                          # React SPA
│       ├── src/{routes,components,hooks,lib,stores,api}
│       ├── package.json
│       └── vite.config.ts
├── packages/
│   └── shared/                       # 可选：共享类型/常量（前后端对齐）
├── docs/                             # 本方案文档
├── infra/
│   ├── docker-compose.yml            # pg + redis + minio + api + worker + web
│   └── initdb/                       # 扩展初始化、种子数据
└── README.md
```

> 用 uv workspace 管理 `apps/api`（Python），pnpm workspace 管理 `apps/web`（Node）。

---

## 10. 部署、可观测、非功能

### 10.1 本地与生产

```yaml
# infra/docker-compose.yml（要点）
services:
  postgres:   # postgres:16 + pgvector 扩展，挂载 initdb 创建 vector/pg_trgm/pgcrypto
  redis:      # redis:7-alpine
  minio:      # 对象存储
  api:        # uvicorn app.main:app --host 0.0.0.0 --port 8000
  worker:     # arq app.workers.settings.WorkerSettings
  web:        # pnpm build && nginx 托管 dist
```

生产演进：API 与 worker 独立扩缩容；PG 用托管版（读副本给检索）；
Redis 用托管版；对象存储用云 OSS。**Agent 层可单独拆成服务**（因为已通过 Repository 协议解耦）。

#### 10.1.1 私有化交付路径（券商/基金 P0 客户的硬要求）

`02-audience.md` 把「券商/基金分析师」列为 P0，而这类客户要求**私有化部署 / 数据不出域 / 审计留痕**。
v1 的 SaaS 架构必须能闭网运行，因此以下组件**必须可替换**，从第一行代码起就走抽象：

| 组件 | SaaS | 私有化 | 抽象方式 |
| --- | --- | --- | --- |
| LLM | 火山方舟 Ark（OpenAI 兼容）· `doubao-seed-evolving` | 自建 vLLM / Ollama 的 OpenAI 兼容端点 | ✅ `ModelProvider` 已落地（`app/services/model_provider.py`），只改 `OPENAI_BASE_URL` |
| Embedding | `doubao-embedding-vision`（实测 2048 维） | 本地 BGE-M3 | ✅ 同上，只改 `EMBEDDING_MODEL` / `EMBEDDING_DIM` |
| 可观测 | LangSmith | **Langfuse 自托管** | `Tracer` 协议；`agent_runs.trace_url` 存各自链接 |
| 对象存储 | 云 OSS | MinIO（已在 compose 中） | S3 兼容接口，天然一致 |
| 凭据加密 | KMS | 本地 Fernet（密钥由部署方注入） | `SecretsProvider` 协议 |
| 外部检索 | Tavily / 博查 | 关闭，仅用已入库资讯 | capability 开关 |

> 约束：`compliance_rules` / `audit_logs` 在**两种部署下行为必须一致**——这是企业版的核心卖点，
> 不能做成"SaaS 版才有"。

### 10.2 可观测

| 维度 | 方案 |
| --- | --- |
| LLM trace | LangSmith（每次 run 记录 `run_id`，业务表存链接） |
| 结构化日志 | structlog，字段含 `request_id / run_id / connector_id / user_id` |
| 指标 | Prometheus：同步条数/耗时、检查延迟、写作时长、token 消耗、失败率 |
| 成本 | 按 run 累计 token 与费用，写入 `usage_records`，UI 出看板 |
| 告警 | 同步连续失败、blocker 率突增、单 run 费用超阈值 |

### 10.3 关键非功能

| 项 | 设计 |
| --- | --- |
| **幂等** | ODS 用 `unique(connector_id, external_id)`；DWD 用 `content_hash` 唯一索引 + upsert |
| **并发** | 同 connector 串行（分布式锁）；检查/写作任务并行受队列并发上限控制（arq `max_jobs`，见 §5.4）；**单批检查并发上限 5 条**（20 条排队而非同时打满 LLM） |
| **限流** | connector 内 token bucket；API 侧按用户配额；LLM 调用失败退避 + 熔断 |
| **缓存** | ★ 事实卡片按 **`news_item_id`** 缓存（资讯级基线，与点评无关，见 §5.2 修订）；embedding 按 `content_hash` 缓存；热点资讯详情 Redis 缓存 |
| **成本控制** | `usage_records` 按 run 实时累计；**硬配额上限**（超额直接拒绝而非提示），见 `01-product-plan.md` §6；单 run 费用超阈值即中断并告警 |
| **安全** | 连接器凭据加密存储（Fernet / KMS）；RLS 或应用层强制 `user_id` 过滤；审计日志 |
| **合规** | 系统级 prompt 硬约束 + `compliance` 轨道 + 红线词库 + 导出时 AI 标识 + `audit_logs` 留痕 |
| **数据保留** | ODS 原始层按需归档（对象存储冷存）；`news_items` 按月分区（量大后） |

---

## 11. 实施顺序（工程视角）

```mermaid
gantt
    title 实施路线（工程视角）
    dateFormat  YYYY-MM-DD
    section 底座
    uv骨架/FastAPI/SQLAlchemy/Alembic      :a1, 2026-09-21, 4d
    Connector抽象层 + Registry             :a2, after a1, 3d
    TushareConnector + ODS/DWD落库          :a3, after a2, 5d
    打标聚类(ScoutAgent) + 定时同步         :a4, after a3, 4d
    section 观点闭环
    点评编辑器 + 版本表                     :b1, after a4, 4d
    ResearcherAgent (FactCard)             :b2, after b1, 5d
    ReviewerAgent 三轨 + 报告UI             :b3, after b2, 8d
    section 写作
    提示词管理 + PromptCompiler             :c1, after b3, 4d
    WriterAgent (DeepAgent) + compose_graph :c2, after c1, 8d
    流式UI + 版本diff + 导出 + 可追溯        :c3, after c2, 6d
```

### 技术风险前置验证（Spike，各 1~2 天）

1. ~~**tushare 资讯接口权限与数据质量真机验证**~~ —— ✅ **已完成**（2026-09-18），结论见 §4.4.1：
   `news` 静默返回 0、`anns_d`/`npr`/`research_report` 无权限、`major_news`/`cctv_news`/行情类可用。
2. **LangGraph interrupt + Postgres checkpointer 端到端验证** —— HITL 是核心体验，必须最先验证。
   **且必须验证"interrupt 后 arq job 结束、resume 起新 job"这条路径**（见 §5.4）。
3. **deepagents 虚拟文件系统在后端（非内存）下的持久化验证** —— 决定长文写作能否断点续跑。
4. **中文向量模型选型** —— 如 BGE-M3 / Qwen3-Embedding，确认维度与检索效果（**定完再写死 `vector(N)`**，换维度要重建 HNSW）。
5. **结构化输出稳定性压测** —— `with_structured_output` 在长文本上的失败率与重试策略。
6. **★ deepagents `skills` 参数形态验证** —— `skills` 实际接收的是**目录路径**（`SKILL.md` 所在目录）而非字符串/对象，
   与 §5.3 伪代码里的 `skills=[state["prompt_bundle"]["skill"]]` 可能不匹配。
   需确认：用户动态编译的提示词包能否走 `StateBackend` 虚拟路径，或必须落盘到临时目录。**这个不确定会直接阻塞 M3。**
7. **★ 单篇成本真机测量** —— 跑一次完整 compose（brief + outline + 5 段 + 复核 + 风格），
   实测 token 与耗时，回填定价模型。这是唯一可能推翻商业模型的数据。
