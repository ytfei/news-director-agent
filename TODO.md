# TODO · 主理人 Agent

> 状态：**M1 ✅ 数据底座 · M2 ✅ 素材 / 批注 / 体检 / 选题（检查为规则版）· 模型层 ✅ 已接入**
> 最后更新：2026-09-24
> 相关文档：`docs/01`~`docs/06`；可点击原型：`prototype/`

---

## 0. 进度总览

| 阶段 | 目标 | 状态 | 证据 |
| --- | --- | --- | --- |
| 原型 | 先理清交互 / 流程 / 功能结构 | ✅ | `prototype/`（15 页，含就地标记素材与就地批注） |
| 规格提炼 | 原型 → 需求 / 流程 / 接口 / 表 | ✅ | `docs/06-prototype-to-impl.md` |
| **M1 数据底座** | 资讯进得来、看得见 | ✅ | tushare 真机同步 + 资讯流 + 收藏评级 |
| **M2 观点闭环** | 素材 → 批注 → 检查 → 选题 | ✅ 规则版 | 迁移 0003/0004、`/api/v1` 26 条路径、9 个前端页面 |
| M3 自动写作 | 文章能出 | ⬜ 占位 | `POST /projects/{id}/compose` 只做准入校验 + run 建档 |
| 容器化与部署 | 一条命令起整套 | ✅ | `make up`（web :8080 / api :8000）+ `make doctor` 自检 |
| M0 假设验证 | 用户愿不愿意先写点评 | ⬜ **未执行（进 M3 前的 Gate）** | — |

**一句话**：现在可以完整走通「挑素材 → 写批注 → 体检 → 建选题 → 触发写作（待接）」，缺的是 Agent 层与写作台。

---

## 1. 已完成

### 1.1 M1 · 数据底座

| 项 | 状态 |
| --- | --- |
| uv + Python 3.12 + FastAPI + SQLAlchemy 2.0 async 骨架 | ✅ |
| 数据源抽象层（Protocol + Registry + `@register`） | ✅ |
| TushareConnector（权限探测、限流、分段续拉） | ✅ |
| ODS/DWD 两级落库 + 跨源去重（追加来源而非丢弃） | ✅ |
| arq worker（sync / enrich + cron） | ✅ |
| 资讯与数据源 REST API | ✅ |
| 真机同步验证（fetched 1628 / inserted 1578 / duplicated 50） | ✅ |

### 1.2 交互原型（2026-09-19）

- `prototype/` 共 15 个页面 + 1 个原型地图（信息架构 / 11 步流程 / 状态机 / 交互约定）
- 核心链路可点击走通：资讯中心勾选 → 工作台批注 → 提交检查 → 体检报告处置 → 选题 → 大纲 HITL → 流式成稿
- 状态存 localStorage，可重置复现

### 1.3 M2 · 素材 → 批注 → 体检 → 选题（2026-09-20）

**数据库**（16 → **30 张表**，迁移 4 个）

| 组 | 表 |
| --- | --- |
| 素材与主题 | `topics` `materials` `material_topics`（+ 0004 预置 15 个系统主题） |
| 批注 | `annotations` `annotation_versions` |
| 事实基线 | `fact_cards` `fact_card_claims` |
| 体检报告 | `review_reports` `review_findings` |
| 选题 / 提示词 / 稿件 | `projects` `project_materials` `prompt_templates`（seed 4 套官方模板）`articles` `article_versions` |

**接口**（`/api/v1` 下 26 条路径）

| 组 | 接口 |
| --- | --- |
| 素材 | `GET/POST /materials`（日期 / 评分 / 主题 / 有无点评 四维筛选）、`GET/PATCH/DELETE /materials/{id}`、`GET /materials/stats`、`GET/POST /topics` |
| 批注 | `GET/PUT /materials/{id}/annotation`（正文变动自动升版本并退回 draft）、`GET /annotations/{id}/versions`、`POST /annotations/check` |
| 体检 | `GET /reviews`、`GET /reviews/{id}`、`POST /reviews/findings/{id}/resolve` |
| 事实 | `GET/PUT /news/{id}/fact-card`（写入时强制"无 evidence 不得标 verified"） |
| 选题 | `GET/POST /projects`（列表带扁平统计，避免 N+1）、`GET/PATCH /projects/{id}`、`POST/DELETE /projects/{id}/materials`、`POST /projects/{id}/compose` |
| 提示词 | `GET/POST /prompts` |
| 既有接口改动 | `GET /news` / `GET /news/{id}` 直接返回 `material` + `annotation` + `fact_card` 徽标 |

**检查引擎（规则版三轨）** —— 接口与 finding 结构按最终形态定死，换 ReviewerAgent 时**不改表、不改协议**

| 轨道 | 取向 | v1 规则 |
| --- | --- | --- |
| `compliance` | 高召回 | 红线词库（骗局 / 造假 / 操纵 / 内幕 / 荐股 / 目标价…）→ blocker |
| `logic` | 折中 | 绝对化断言 → high；以偏概全 → medium |
| `fact` | 高精度 | 只报与 FactCard `contradicted` 冲突的数值，或带单位却查无出处的数值 |

已实现的产品语义：`verdict` 由未处置 finding 派生 · blocker 未处置直接拦写作 · 驳回必填理由且**同一问题不再重复报** · 采纳会改写正文并生成新版本。

**前端**（React 19 + Vite + Tailwind v4 + TanStack Query，9 个页面）

| 路由 | 页面 | 关键实现 |
| --- | --- | --- |
| `/` | 今日收件箱 | 今日素材统计、待办、评分最高未批注、选题概览 |
| `/news` | **资讯中心** | 三视图（全部 / 我的素材 / 待批注）、**卡片内联标记素材**（评分 1~10 + 主题 + 日期）、**内联批注**、批量加入素材 |
| `/news/:id` | 资讯详情 | 全文 + 事件簇各源差异 + FactCard |
| `/workbench` | 点评工作台 | 数据源 = 素材库，按日期 / 评分 / 主题筛选，右侧常显原文与事实基线 |
| `/reviews` | AI 体检报告 | 划词高亮、采纳 / 驳回（必填理由）/ 忽略、verdict 实时变化 |
| `/projects` | 选题 | 素材挑选器、可写作性判定、`opinion` / `digest` 模式提示 |
| `/projects/:id/compose` | AI 写作 | 占位：呈现 WriterAgent 的真实输入（brief），不画假界面 |
| `/prompts` | 提示词 | 按 category 分组、版本号、新建 |
| `/settings/connectors` | 数据源 | **能力声明驱动的配置表单**（新增渠道不改前端）、逐来源可用状态、权限探测、手动同步、同步日志 |

### 1.4 容器化与部署（2026-09-20）

| 产物 | 说明 |
| --- | --- |
| `apps/api/Dockerfile` | 3 阶段：`builder`（uv 锁文件装依赖）→ `runtime`（非 root、tini 收信号、HEALTHCHECK）→ `dev`（含 pytest/ruff）。**一个镜像跑 api / worker / migrate 三种角色**，避免依赖漂移 |
| `apps/web/Dockerfile` | `deps`（`npm ci`）→ `build`（`tsc --noEmit && vite build`，类型错就让镜像构建失败）→ `runtime`（nginx 静态托管） |
| `apps/web/nginx/default.conf.template` | SPA 深链回退 · `/api` 反代（`envsubst` 注入上游，**无 CORS**）· SSE 关缓冲 · 静态资源长缓存 · 安全响应头 |
| `docker-compose.yml`（根） | 全栈：postgres / redis / minio / **migrate（一次性）** / api / worker / web。依赖 `service_healthy` + `service_completed_successfully` 编排启动顺序 |
| `infra/docker-compose.yml` | 保留为"仅基础设施"模式（暴露 5433 / 6380 / 9000 给宿主机）—— **与全栈 compose 端口不冲突，可同时运行** |
| `Makefile` | 42 个目标（含 `help`），`make` 即列全部：准备 / 本地开发 / 测试与质量 / Docker 构建部署 / 清理 |
| `apps/api/scripts/doctor.py` | 部署前自检：配置 → DB → Redis → 迁移版本 → **向量维度一致性** → 向量索引 → 关键表 → 预置数据。可 `docker compose exec api python scripts/doctor.py` 在真实环境跑 |

**实测记录**（全新数据卷，从零拉起）

```
$ make up
 Container nda-app-postgres  Healthy      Container nda-app-migrate  Exited(0)
 Container nda-app-redis     Healthy      Container nda-app-api      Healthy
 Container nda-app-minio     Healthy      Container nda-app-worker   Started
 Container nda-app-web       Started

$ docker compose exec -T postgres psql -U nda -d nda -c "select count(*) from pg_tables where schemaname='public'"
 31   （30 张业务表 + alembic_version）      alembic_version = 0004_system_topics
$ docker compose exec -T api python scripts/doctor.py   →  自检通过
$ curl localhost:8080/api/v1/topics                     →  200（经 nginx 反代）
$ curl -X POST localhost:8080/api/v1/topics             →  201（写路径通）
$ curl localhost:8080/workbench                         →  200（SPA 深链回退生效）
```

### 1.5 验收口径（可复现）

```bash
cd apps/api
uv run alembic upgrade head          # 0001 → 0004
uv run pytest tests/ -q              # 18 passed
uv run ruff check app                # All checks passed
uv run alembic check                 # ✅ 无差异（P0-2 已解决：降维 1024 + HNSW 已建；
                                     #    另修复 minhash 索引模型定义缺失导致的误报漂移）

cd ../web
npm run build                        # tsc --noEmit + vite build 通过
```

- 规则单测（8 条，无需 DB）：三轨严重度取向、verdict 派生、驳回过的不再拦截
- M2 集成测试（5 条，走真库）：幂等标记素材 → 主题筛选 → 批注版本 → 检查出 blocker → 红线未处置时 compose 返回 409 → 采纳/驳回 → 复检 → 可写作 → 触发写作；「无点评素材直接写作（digest 模式）」；无批注时检查返回 422；系统主题与统计；官方提示词已 seed
- M1 冒烟（5 条）：注册表 / 标准码 / 归一化纯函数 / health + available，以及一条**真机 tushare 同步**（依赖 `.env` 里的 `TUSHARE_TOKEN`，缺失时会 skip —— 注意 skip 与 pass 的区别）

### 1.6 模型层（2026-09-24）

统一走 **OpenAI 兼容协议**（火山方舟 Ark），`app/services/model_provider.py`。

| 项 | 说明 |
| --- | --- |
| 三档对话 | `pro` 深度推理（1M）／ `turbo` 均衡主力（256k，**默认**）／ `lite` 轻量批量（256k） |
| 向量 | `doubao-embedding-vision` —— 实测 **2048 维** |
| 抽象 | `ModelProvider`（chat / chat_json / embed / embed_one），无 key 时降级不崩溃 |
| 路由 | `Task` 枚举 → `DEFAULT_TIER`，可用 `LLM_TIER_OVERRIDES` 覆盖（见 `docs/04 §5.6`） |
| 接入点 | `enrich_service` 真实写入 `news_items.embedding`（已验证 `vector_dims=2048`） |
| 降级策略 | 模型不可用 → 规则结果照常入库，embedding 留空，同步链路不被拖垮 |
| 自检 | `make models`（真机探测，含维度一致性与 reasoning 占比）；`make doctor` 只校验配置不花钱 |

**实测（2026-09-25，同一 prompt 对比两次，结论一致）**

| 任务 | pro | turbo | lite |
| --- | --- | --- | --- |
| 简单分类 | 194 tok / 6.5s | **36 tok / 2.1s** | 407 tok / 8.9s |
| 事实核查 | 4285 tok / **108s** | 3613 tok / 56s | 3055 tok / 48s |
| 核查质量 | 3/3 命中 | 3/3 命中 | 3/3 命中 |

三条结论：

1. **三款都是推理模型**（reasoning 占 97~100%），这个接入点上没有"非推理"选项
2. **turbo 是甜点**：简单任务只要 36 tok，是 pro 的 1/5、lite 的 1/11
3. **反直觉**：lite 在简单任务上**并不比 turbo 省**（407 vs 36）
   —— "轻量"是能力定位，不是思考更少

**★ 延迟红线（最重要的约束）**：核查类任务单次 **48~108 秒**，
远超「检查单条 < 8s」。由此确定的两条硬规则（已写进 `docs/04 §5.6`）：

- [x] 默认检查路径保留规则版（`rules-v1`），LLM 检查作为可选"深度检查"
- [ ] **深度检查必须异步**（arq + SSE 进度），不能在请求里同步等待 —— 待实现
- [ ] 写作（pro 规划）同理，必须异步流式
- [ ] `ENRICH_USE_LLM` 目前默认 false；turbo 分类仅 36 tok，M2 收尾时可评估打开

### 1.7 验收环境与首次验收结果（2026-09-26）

**一条命令验收**：`make acceptance`（脚本 `apps/api/scripts/acceptance.py`）

设计取舍：**统计类指标只读开发库**（不写入），**功能链路在独立测试库 `nda_test` 跑**
（复用集成测试），因此验收过程不会污染真实数据。不达标时退出码 1，可直接接 CI。

| 验收项 | 实测 | 阈值 | 判定 |
| --- | --- | --- | --- |
| 业务表 / 迁移版本 / 预置数据 | 32 表 · head=0006 · 主题 15 · 提示词 4 | — | ✅ |
| 同步 | 15982 条 · 最近一次 success | — | ✅ |
| **重复率** | **3.07%**（50/1628） | < 2% | ❌ |
| **多源簇占比** | 0.20%（31/15861）→ **1.76%（261/14803）** | > 1.5% | ❌ → ✅（见 P0-1） |
| 向量化覆盖 | 1 条（0.0%，存量待补跑 enrich） | > 0 | ⚠️ |
| 功能链路（集成测试） | 79 passed / 0 failed / 0 skipped | 0 failed | ✅ |
| 前端构建 | `tsc --noEmit` + `vite build` 通过 | 0 error | ✅ |

**结论**：功能链路与前端可用；**两项质量指标不达标，且指向同一处**——
规则版 simhash 的阈值与去重策略（TODO P0-1）。这两项不解决，"另有 N 家报道 /
展开看各源差异"就是空功能，M1 的验收口径也无法闭环。

> 验收脚本自身也修了一处取样 bug：重复率原本取"最近一次同步"，
> 若该次为空同步会算出 `0/0` 的**假绿值**；现改为取最近一次 `fetched > 0` 的同步。

### 1.8 多来源接入与对比（2026-09-26）

**新增来源**：`tushare.flash` 默认来源改为 新浪财经 / 华尔街见闻 / 东方财富 + 财联社。

**对比脚本**：`scripts/compare_sources.py`（只读、不落库）

```
uv run python scripts/compare_sources.py --hours 12
uv run python scripts/compare_sources.py --srcs sina,eastmoney --hours 24
```

**实测：12 小时窗口各源数据量**

| 来源 | 条数 | 标题填充率 |
| --- | --- | --- |
| 新浪财经 sina | 160 | **0%** |
| 东方财富 eastmoney | 91 | 100% |
| 金融界 jinrongjie | 49 | 63% |
| 同花顺 10jqka | 48 | 100% |
| 华尔街见闻 wallstreetcn | 46 | 72% |
| 第一财经 yicai | 34 | 100% |
| 财联社 cls | 6 | 83% |
| 云财经 / 凤凰新闻 | 0 | — |

**跨源重叠**（标题 Jaccard ≥ 0.6 视为同一条）：

- 同花顺 × 东方财富 **73%**（高度重复）
- 东方财富 × 第一财经 59%、财联社 × 第一财经 50%
- 其余组合 20~40%

→ 结论：多源确实报道相同事件（交叉验证的原料充足），但**重复度高**，
因此 L3 转载合并不是可选项而是必需品。

**同步验证**（四源、重置游标、12h）：fetched 298 / inserted 17 / duplicated 281；
多来源条目（`source_refs>=2`）**+236**，说明跨源合并生效。

**过程中发现并修复 4 个缺陷**：

| # | 问题 | 处置 |
| --- | --- | --- |
| D18 | **新浪 / 华尔街见闻的 `title` 恒为 None** → `external_id`（含 title）退化，同一秒多条快讯幂等键撞车 | `title_from_content()`：从正文取首句兜底，且在**算幂等键之前**补全 |
| D19 | `can't compare offset-naive and offset-aware datetimes`：调用方窗口是 naive、来源游标是 aware | 连接器入口 `ensure_tz()` 统一时区 |
| D20 | **`source_refs` 追加不幂等**：同一来源每次同步都再追加，实测长度达 25/39，让「另有 N 家报道」失真 | 改为按**来源名**判重后追加；存量用 `--clean-refs` 清理（已处理 5988 条，均值 2.38） |
| D21 | 同步锁 TTL 3600s 过长：进程崩溃后 1 小时内无法重跑（本次已遇到，只能手动 `redis-cli del`） | ✅ **已修（2026-09-27）**：改为**短 TTL（300s）+ 心跳续约** —— 崩溃后最多 5 分钟自动可重跑，长任务由心跳每 TTL/3 续期不会丢锁；并用唯一 token 保证只有持有者能释放（否则 A 超时后的一次释放会删掉 B 的锁）。`app/core/redis.py::SyncLock`，6 条测试覆盖崩溃恢复与续约 |

> 存量仍有极个别异常条目（`max 39`，历史无名来源堆积）；新数据已幂等，不影响。

---

## 2. 本次交付暴露的问题

### 2.1 已修复

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| D1 | 保存素材/批注后报 `MissingGreenlet` | `server_default` 与 `onupdate=func.now()` 的字段在 `flush` 后未回读，异步下隐式 IO | 仓储层写后统一 `refresh`；测试与注释固化该约定 |
| D2 | 触发写作时 `Object of type UUID is not JSON serializable` | `agent_runs.input` 里塞了 UUID 对象（只在真正 compose 时才暴露） | JSONB 落库前统一 `str()` |
| D3 | **集成测试被静默 skip，假装通过** | `engine` 是模块级，pytest-asyncio 每测试一个事件循环，跨循环复用 asyncpg 连接 | 新增 `tests/conftest.py` 每测试后 `engine.dispose()` |
| D4 | 素材主题从零开始打，跨日期无聚类价值 | 未预置主题词表 | 迁移 0004 预置 15 个系统主题 |
| D5 | `docker compose up` 拉不到 `minio/minio` | MinIO 已从 Docker Hub 下线，镜像只在 Quay | 两个 compose 都改 `quay.io/minio/minio`；健康检查改用内置 curl（服务镜像没有 `mc`） |
| D6 | worker 容器永远 `unhealthy` | 镜像级 HEALTHCHECK 打的是 uvicorn `/health`，worker 不监听端口 | 改为读 arq 自带健康 beacon（见 D14） |
| D7 | `docker compose up -d api` 重建后，前端全站 502 | nginx 只在启动时解析上游主机名，容器重建 IP 变了 | nginx 改用 `resolver` + 变量 `proxy_pass`，按请求重新解析；已用 `--force-recreate api` 验证 |
| D14 | worker 没有可用的健康探针 | arq **本来就提供** beacon：`WorkerSettings.health_check_interval=30` 每 30s 写 `arq:queue:health-check`，值为运行统计、TTL = interval+1s（arq 0.28.0）。缺的只是"读它"的探针 | compose 加 healthcheck 直接读该 key。「key 存在」⟺「worker 活着」，进程卡死或被杀后 31s 内自动消失——比只看日志可靠（日志只能发现"退出"，发现不了"卡住但没退出"）。已验证：删 key → 探针转 False |

> D3 最危险：`pytest` 报"通过"，但 4 条集成测试其实一条都没跑。修掉后立刻暴露了 D2 与 D4。

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| D16 | 新建的库跑 `alembic upgrade head` 在第一个 VECTOR 列失败（`type "vector" does not exist`） | 扩展只在 `infra/initdb/00-extensions.sql` 里对**默认库**执行一次，任何新建库都没有 → 全新环境部署 / CI 建临时库 / 新建测试库都会踩到 | `alembic/env.py` 的 `ensure_extensions()` 在所有迁移之前统一创建 + 迁移 `0006_ensure_extensions`（幂等兜底） |
| D17 | 迁移日志全部 `Running upgrade ... 成功`，但库里 **0 张表** | 在 `context.begin_transaction()` **之前**用同一个连接执行 DDL，连接进入事务态，Alembic 认为事务由外部管理而不提交，连接关闭时整体回滚（**静默失败，最难查**） | `ensure_extensions` 改用**独立连接**并显式 `commit()`，迁移连接保持干净 |

### 2.2 待修（已定位，进入 M2 收尾）

| # | 现象 | 影响 | 方向 |
| --- | --- | --- | --- |
| D8 | 采纳建议 / 改写正文后，旧报告的 `span_start/span_end` 会错位 | 体检页高亮画错位置 | 报告增加 `is_stale` 标记（版本号 ≠ 当前版本即提示"报告已过期，请复检"） |
| D9 | 驳回记忆永久化：正文大改后仍屏蔽同一问题 | 用户改了写法却拿不到新结论 | 正文变更超过阈值（如 diff > 30%）时清空该点评的驳回记忆 |
| D10 | 前端用 `window.location.href` 跳转 | 绕过 react-router，丢失 SPA 状态 | 统一改 `useNavigate` |
| D11 | 单批检查上限 20 / 并发 ≤5 只在文档 | 批量提交可能打满 LLM 造成成本尖峰 | 服务端 enforce + 返回 429/422 |
| D12 | `/materials` 用 `limit/offset`，无游标 | 素材上量后翻页退化 | 改用 `before_date + offset` 复合游标 |
| D13 | 集成测试写进开发库 | 开发库被测试数据污染 | ✅ **已解决（2026-09-26）**：独立测试库 `nda_test` + `make test-db-create` / `make test-db-reset`；conftest 在导入 app 前切换 `DATABASE_URL`（`USE_TEST_DB=0` 可强制走开发库）。实测：开发库 15982 → 15982 不变，测试数据落在 nda_test |
| D15 | 镜像 EXPOSE 让 worker 在 `docker compose ps` 里显示 `8000/tcp` | 误导（worker 不监听端口） | 多角色共用镜像的固有代价，或在 compose 覆盖标注 |

---

## 3. P0 · 阻塞（不解决会带病进 M3）

### 1. ★ 事件簇 —— 已改为分层方案，多源簇提升 8.4 倍（2026-09-26）

**原状**：15982 条 → 15861 个簇，几乎一对一；`source_count>=2` 的簇仅 **31 个（0.20%）**，
"另有 N 家报道 / 展开看各源差异"实际是空功能。

**根因（两个，缺一不可）**：

1. **概念混淆**：`_assign_cluster` 用同一个 simhash 阈值同时判「转载」和「同事件」。
   这两者必须分开 —— 转载要**合并展示**（只留一条），同事件不同角度要**都保留**
   （信息互补，正是交叉验证的素材）。
2. **信号缺失**：库里 `entities` / `keywords` / `industries` **15982 条无一有值**，
   embedding 也几乎没有 → 打分恒为 0 → 每条都新建簇。

**已实现**（`app/lib/dedupe.py`，四层）：

| 层 | 判定什么 | 方法 | 阈值 |
| --- | --- | --- | --- |
| L1 | 文本可比 | 去【】来源前缀 / NFKC 全半角 / 去标点（**保留小数点**） | — |
| L2 | 完全相同 | `content_hash`（保持原语义，存量 hash 不失配） | 精确 |
| **L3** | 同一篇的转载 → **合并展示** | MinHash（3-gram）Jaccard + 简化 LSH 桶粗筛 | 0.75（精确率优先） |
| **L4** | 同事件不同角度 → **都保留** | 标题 0.55 + embedding 0.25 + 实体 0.10 + 关键词 0.05 + 时间 0.05 | 0.32 |

关键设计：
- **时间是硬门槛**，不是软权重。只给 0.10 权重时，相隔 10 天、实体关键词完全相同的
  两条仍能拿 0.85 分，但那已经是另一件事了。
- L4 只与**簇代表**比较（不是簇内所有条目），这是性能关键。
- `member_count`（独立报道数）与 `duplicate_count`（转载数）已分开。
- 中文用 **3-gram**（实测 5-gram 对渠道改写只有 0.15 重合，3-gram 明显更鲁棒）。

**实测效果**（全量重建 15982 条）：

| 指标 | 改造前 | 改造后 |
| --- | --- | --- |
| 多源簇（source_count≥2） | 31 | **261（8.4 倍）** |
| 多源簇占比 | 0.20% | **1.76%（8.8 倍）** |
| 多条簇（member_count≥2） | 68 | 858 |

抽样验证：贝达药业 / 新华制药 / 宁德时代造谣 / 文旅部规划等簇均为真同事件，
且新浪带【】前缀的标题也被正确匹配（归一化生效）。

**剩余（不再阻塞，但决定上限）**：

- [ ] **标注集**：抽 300 对人工标「同事件 / 不同事件」，扫阈值画 P/R 曲线
      —— 当前 0.32 是"特征不全"下的起点，**未经标定**
- [ ] **补实体抽取**：entities 全空，L4 少了 0.10 权重的信号
- [ ] **embedding 补跑**：存量跑完，L4 才有 0.25 权重的语义信号
- [ ] 标定后上调验收线（现 1.5%，是可达标线而非理想线）
- [ ] 长期：由 `ScoutAgent` 做模型判定，表结构不变

### 2. ✅ pgvector 索引维度超限 —— 已彻底解决：Matryoshka 降维 1024 + HNSW 索引已建（2026-09-28）

**最终方案：模型不用换，只需调用时多传一个 `dimensions=1024` 参数。**

- [x] `doubao-embedding-vision` 原生 2048 维，但**支持 Matryoshka 降维** ——
      传 `dimensions=1024` 由模型端直接输出 1024 维（前 N 维本身即有效的低维表示，**不是简单截断**）
- [x] 代码改动：`app/services/model_provider.py::embed` 增加 `dimensions=settings.EMBEDDING_DIM`
      —— **路径与 model id 均不变**
- [x] 配置：`EMBEDDING_DIM` 2048 → **1024**（`config.py` / `.env` / `.env.example` 三处统一）
- [x] 迁移 `0008_embedding_dim_1024`：清空存量向量 → `vector(2048)` → `vector(1024)` → **建 HNSW 索引**
      （幂等：全新环境从 0001 起跑时列已是 1024，本迁移全部跳过）
- [x] 真机验证：`embed_one()` 返回 **1024 维**，与 `EMBEDDING_DIM` 一致
- [x] 库中 `news_items.embedding` / `news_clusters.centroid` 均为 `vector(1024)`；
      `ix_news_items_embedding` / `ix_news_clusters_centroid` **（hnsw）均已建立**
- [x] 回归：`pytest` **96 passed**；`ruff check app scripts` **All checks passed**
- [x] 文档已同步（`docs/README` 技术栈、`docs/04` 选型表与私有化表、`docs/05` §1 与 §4.8、`docs/07` D1/H7）

**三重收益**：存储减半（8KB→4KB/条）、距离计算减半、**检索从 O(n) 全表扫描变为 O(log n)**。

**历史背景（保留，避免重犯）**：

- 曾三处值不一致：库 `vector(2048)` / compose 环境变量 `2048` / `.env` 文件 `1024`（被静默覆盖）
  → 换台机器跑就会用 1024 维去写 2048 维的列并报错。现已全部统一为 **1024**。
- `docs/05` 早期写「`vector(1024)`」只是预期值，与当时实际的 2048 不符；现在名实相符。

**遗留（不再阻塞，归入 P1-9 同步指标）**：

- [ ] **存量向量补跑**：降维后存量已清空，当前覆盖 **0.0%**，需跑一次全量 `enrich`
- [ ] 补跑后验证 `make acceptance` 的「向量化覆盖」指标从 0.0% 上去

### 3. tushare 快讯「返回 0 行」 —— 已于 2026-09-20 定位并修复

**原判断（记录在案，避免重犯）**：把 `news` 的"返回 0 行、不报错"当成了**权限问题**。
实际是**我们自己的调用参数写错**，两个错误各自都会让接口返回空：

| 错误 | 旧实现 | 官方规格（doc 143） |
| --- | --- | --- |
| `src` 参数 | 默认不传 | **必选**，9 个来源之一 |
| 时间格式 | `%Y%m%d %H%M%S` | `%Y-%m-%d %H:%M:%S` |

修正后真机结果：3 天窗口抓取 **3842 条 / 落库 3799 条**，来源正确落到
财联社 / 新浪财经（再验 10jqka 同花顺亦有数据）。

- [x] 拆出独立的 `tushare.flash` 连接器（多来源可配、按来源独立限流与游标）
- [x] 修正 `src` 必传 + 时间格式
- [x] 单次 1500 条触顶 → 自动二分细分窗口，避免静默丢数据
- [x] 顺带修掉 pandas 脏值炸 jsonb（`float('nan')` → 非法 JSON 被 PG 拒收，`json_safe` 统一归一）
- [x] 前端逐来源展示可用状态（不再是笼统的"接口无权限"）
- [ ] **仍无权限**：`anns_d` / `npr` / `research_report`（公告 / 政策 / 研报三类素材拿不到）
- [ ] 评估更高积分 token 成本，或接第二数据源（RSS / 交易所公告 / 政府网政策）
- **验收**：至少覆盖「快讯 + 公告 + 政策」三类 `content_type` —— **快讯 ✅**，公告/政策仍待解决

> **教训（写进 `docs/04 §4.4.1`）**：接不上某个数据源时，先怀疑自己的参数，
> 再怀疑对方权限。"返回 0 行"和"无权限"是两种完全不同的故障，
> 混为一谈会让我们白白绕开一个本来可用的数据源。

### 4. 鉴权未接

- **现状**：`X-User-Id` 头 + dev 默认用户，无 JWT / 无租户隔离。**M2 所有新表（素材/批注/选题）都带 `user_id` 并已按用户过滤**，但身份本身可伪造。
- [ ] 接入 JWT（含 refresh）
- [ ] 团队版启用 RLS；`users.org_id` / `projects.org_id` 已预留，接多租户时补 `orgs` 表

---

## 4. P1 · M2 收尾（建议 1~1.5 周）

### 5. 兴趣画像与召回（前端唯一没落地的页面）

- [ ] `user_interests` CRUD 接口 + 画像页
- [ ] 收件箱从"按时间倒序"改为"重要度 × 画像匹配 × 历史互动"召回
- [ ] 命中即打分的可解释性（告诉用户"为什么推给你"）

### 6. 素材 / 批注体验收尾

- [ ] D8 报告过期提示、D9 驳回记忆失效策略、D10 路由跳转、D11 批量上限 enforce、D12 素材分页游标
- [ ] 批注撤销 / 版本回退 UI（接口已有 `GET /annotations/{id}/versions`）
- [ ] 「AI 提示问题」与「引用事实」入口（原型有，前端尚未接）

### 7. 配额与成本硬上限

- [ ] 按 run 累计 token 与费用写入 `usage_records`（表已建，无累计逻辑）
- [ ] 超额**直接拒绝**（不是软提示）—— ¥199/月"无限写作"存在亏损风险
- [ ] 单次 compose / 单次检查成本实测（Spike #7），回填定价模型
- [ ] 用量看板页（原型有，前端未做）

### 8. 检查质量的评测与回归

- [ ] 评测集：事实 100 条 / 逻辑 50 条 / 合规红线 50 条，接 LangSmith dataset
- [ ] **三轨分别统计**：事实误报率 < 15%（高精度）、合规召回率 > 95%（高召回）
- [ ] 规则 → Agent 的替换前后对比（当前规则版的误报率尚未测过，M2 验收指标未达成验证）

### 9. 同步指标未达标

- **现象**：重复率 **3%**（50/1628），M1 验收要求 **< 2%**。
- [ ] 随 P0-1 归簇 / 去重改进一起解决

### 10. M0 假设验证（**进 M3 前的 Gate**）

- [ ] 20 个种子主理人 Wizard-of-Oz：愿不愿意写点评？一次写几条？建议采纳率能到 50% 吗？
- [ ] 打字 vs 语音碎片转写（影响 M3 编辑器形态）
- **零代码，3~5 天。不达标则回到产品定义，不进 M3。**

---

### 11. 规则版检查 → 真实模型（模型层已就绪，现在可做）

> 前提已具备：`ModelProvider` 可用、embedding 已入库、`TokenUsage` 能统计成本。

- [ ] 用 LLM 替换 `_rules_for` 的三轨，**保留规则版作为兜底与对照**
- [ ] 先做 `fact` 轨（高精度取向）做对照实验：规则 vs 模型的误报率
- [ ] 成本约束：推理模型贵 → 优先配 `LLM_MODEL_LIGHT`；批量检查并发 ≤5（P1-11 待 enforce）
- [ ] 三轨分别统计（事实误报 < 15% / 合规召回 > 95%）
- **验收**：评测集上模型版优于规则版，且单条成本可接受（成本实测依赖这一条，见 P1-7）

---

## 5. P2 · M3 自动写作（建议 3 周）

> 前置：M0 Gate 通过 + P0-4 鉴权 + P1-6 收尾完成

### 11. 提示词 → Skill 包编译
- [ ] `prompt_templates` → `SKILL.md` + 结构化约束（禁用词表 / 必含要素 / few-shot）
- [ ] 按栏目 / 平台按需加载，而不是把全部提示词塞进一次上下文
- [ ] 版本回滚与「测试预览」（当前只有列表 + 新建）

### 12. `WriterAgent` + `compose_graph`
- [ ] **先 Spike 验证 deepagents 的 `skills` 参数形态**（可能阻塞 M3）
- [ ] 素材装载 → `/brief.md` `/facts/*.md` `/style-guide.md` 虚拟文件系统
- [ ] `write_todos` 规划 → 大纲 → 分段并行写作 → 事实复核 → 风格统一 → 标题
- [ ] 护栏：每个事实句必须映射到 FactCard 的 `FactItem`；不生成基线外的数字 / 日期 / 机构名
- [ ] 产出 `citation_map`，落 `articles` + `article_versions`

### 13. HITL 断点 + SSE
- [ ] LangGraph `interrupt` + Postgres checkpointer 端到端验证（Spike #2，核心体验）
- [ ] `compose.outline_ready` → 大纲可编辑 → `Command(resume=...)`
- [ ] `compose.token` 流式（**不落库**，走 Redis pub/sub）
- [ ] `agent_runs.status=waiting_human` 24h 超时清理
- [ ] SSE 事件契约落地（`docs/03` §6）

### 14. 稿件与可追溯
- [ ] 版本 diff（AI 稿 vs 人工稿）、段落重写
- [ ] 导出 MD / HTML / Word，附「AI 辅助撰写」标识
- [ ] 可追溯视图：文章 → 段落 → 批注 → 素材 → 证据

### 15. 工程化
- [x] `docker-compose.yml` 补 `api` / `worker` / `web` / `migrate` 服务（2026-09-20）
- [x] 多阶段 Dockerfile（api 一镜像三角色 + web nginx）、Makefile 33 个目标、`scripts/doctor.py` 部署自检
- [ ] **CI**：ruff + pytest + `alembic check`（`make check` 已提供入口，缺的是流水线；**先解 P0-2，否则 check 必然红**）
- [ ] 测试库隔离 + `seed` / `reset` 脚本（解 D13，也是 CI 的前置条件）
- [ ] 镜像发布到 registry + 多架构构建（当前只在本地 build）
- [ ] HTTPS / 域名 / 反向代理前置（现在 nginx 只提供 HTTP，靠外层网关终止 TLS）
- [ ] 日志聚合与指标（`usage_records` / Prometheus，配 `docker compose logs` 之外的可观测）
- [ ] `enrich_service` 规则版待 `ScoutAgent` 替换
- [ ] `ModelProvider` / `Tracer` / `SecretsProvider` 抽象落代码（私有化前置）
- [ ] LangSmith / Langfuse trace 接入

---

## 6. P3 · M4 沉淀与扩展

- [ ] 观点库 + 观点演化时间线 + 复用
- [ ] `uniqueness` 检查轨道（对接历史观点库）
- [ ] 第二数据源（RSS / 公众号 / 雪球 / 交易所）+ 板块行情
- [ ] 多平台改写（一稿多版）+ 发布对接
- [ ] 风格自学习（从人工编辑 diff 提取偏好，反哺提示词）
- [ ] 团队版（多租户 / 多人协作 / 合规审计）

---

## 附 · 如何复现

```bash
make            # 列出全部命令（42 个）
make doctor     # 先跑这个：配置 / DB / Redis / 迁移 / 向量维度一致性
```

### A. 容器部署（推荐，一条命令起整套）

```bash
cp .env.example .env     # 按需填 TUSHARE_TOKEN
make up                  # → web http://localhost:8080 · api http://localhost:8000/docs
make smoke               # 探活 web / api，并验证 nginx → api 反代
make logs                # 跟随日志
make down                # 停止（保留数据卷）；make down-clean 会清库
```

### B. 本地开发（依赖走 Docker，代码热重载）

```bash
make env                 # 生成 .env（根目录 + apps/api）
make infra               # pg 5433 / redis 6380 / minio 9000-9001
make install             # uv sync + npm ci
make migrate             # 0001 → 0004
make dev-api             # :8000（另开终端）
make dev-worker          # arq 队列（另开终端）
make dev-web             # :5173，/api 反代到 :8000
```

### C. 测试与质量

```bash
make test                # 后端 pytest + 前端 tsc && vite build
make test-unit           # 只跑不依赖 DB 的规则单测
make test-integration    # 只跑集成测试（需 Postgres 已迁移）
make lint                # ruff + alembic check
make check               # 提交前门禁（lint + test）
```

### D. 看交互设计（纯静态，无需后端）

```bash
open prototype/index.html
```

> 两套 compose 可同时运行：`infra/` 暴露 5433/6380/9000 给宿主机（本地开发用），
> 根目录的全栈 compose 把 pg/redis/minio 关在内部网络（部署用），**端口不冲突**。
> 迁移链：`c6fca63ba48f`（M1 核心 16 表）→ `0002_triggers` → `0003_materials`（M2 中枢 14 表）→ `0004_system_topics`（预置主题）。
