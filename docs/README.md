# 主理人 Agent（Curator Agent）— 产品与架构方案

> **一句话定位**：一个以「用户观点」为核心燃料的内容生产工作台 —— 帮内容主理人把
> 「读资讯 → 出观点 → 查错 → 成文」这条链路从每天 3 小时压缩到 30 分钟，
> 且写出来的东西**是"你"的，不是 AI 的**。

---

## 0. 先回答你的两个问题

### Q1：应该做出一个什么样的 Agent？

**不要做"一个" Agent，要做"一个工作流骨架 + 四个专业子 Agent"的混合体。**

| 层 | 是什么 | 形态 | 为什么 |
| --- | --- | --- | --- |
| 编排层 | `Orchestrator` | **确定性工作流**（LangGraph `StateGraph`） | 流程必须可重入、可暂停、可人工干预、可版本化。纯 ReAct 会"跑飞"，产物不可复现 |
| 子 Agent ×4 | 资讯管家 / 事实研究员 / 观点审稿人 / 主笔 | **DeepAgent**（planning + subagent + 虚拟文件系统 + skills） | 每个子 Agent 都需要多步规划、需要落盘中间产物、需要加载不同"技能" |

四个子 Agent 的职责边界（这是本产品的核心资产）：

| Agent | 代号 | 输入 | 输出 | 关键能力 |
| --- | --- | --- | --- | --- |
| 资讯管家 | `ScoutAgent` | 原始数据（tushare / RSS / …） | 归一化资讯 + 标签 + 聚类 + 重要度 | 去重、打标、事件聚类、兴趣召回 |
| 事实研究员 | `ResearcherAgent` | 一条资讯 + 用户点评 | **事实卡片**（可引用证据集） | 检索、交叉验证、时间线还原、关联标的 |
| 观点审稿人 | `ReviewerAgent` | 用户点评 + 事实卡片 | **结构化体检报告** | 事实核查 / 逻辑检查 / 合规风险，三轨并行 |
| 主笔 | `WriterAgent` | 素材集 + 事实卡片 + 用户提示词 | 大纲 → 长文 → 配图建议 | 规划、子代理调度、风格克隆、自我修订 |

**产品的灵魂在 `ReviewerAgent`，护城河在 `WriterAgent` 的"风格克隆"。**
资讯聚合市面上很多，但"把用户的碎片点评变成一篇有观点、无硬伤、像本人口吻的文章"，目前没有好产品。

### Q2：技术栈定版

| 层 | 选型 | 备选 / 说明 |
| --- | --- | --- |
| 包管理 | **uv**（你已定） | 一体化管理 venv + 依赖锁，`uv sync` / `uv run` |
| 语言 | **Python 3.12** | 兼顾生态与性能 |
| Web 框架 | **FastAPI** | 异步原生，天然适配 LangGraph `astream` + SSE |
| Agent 框架 | **LangGraph 1.x**（工作流）+ **deepagents**（子 Agent 封装） | 不直接用 LangChain Chain，Chain 无法表达 HITL 中断 |
| 数据校验 | **Pydantic v2** | 同时用于 API schema 与 Agent 结构化输出（`with_structured_output`） |
| ORM / 迁移 | **SQLAlchemy 2.0 async** + **Alembic**（你已定） | `alembic revision --autogenerate` + 统一 naming_convention |
| 主库 | **PostgreSQL 16** + **pgvector** + **pg_trgm** | 关系 + 向量 + 中文模糊检索一个库搞定，v1 不引入 ES |
| 缓存 / 队列 | **Redis 7** + **arq**（异步任务队列） | arq 是 async 原生，比 Celery 更贴合；若团队熟悉 Celery 可换 |
| 对象存储 | S3 兼容（MinIO 本地 / 云 OSS） | 公告 PDF、导出文章、封面图 |
| **LLM 供应商** | 打标/聚类用 **DeepSeek-V3 / Qwen-Plus**；检查/写作用 **Claude Sonnet 4.x 或 GPT-4o 级**；embedding 用 **BGE-M3 / Qwen3-Embedding** | 中文财经场景 + 成本可控。走 `ModelProvider` 抽象，私有化时换本地 Qwen |
| 网页检索 | Tavily / 博查 | ResearcherAgent 的 `web_probe` 依赖它；没有它，事实核查被锁死在 tushare 内 |
| 可观测 | **LangSmith** + structlog（私有化换 **Langfuse 自托管**） | LangGraph 原生 trace，按 `run_id` 关联业务记录 |
| 前端 | **React 19 + Vite + TypeScript（SPA）** | **不用 Astro 做主体**，理由见 `04-architecture.md` §8 |
| UI / 状态 | Tailwind v4 + shadcn/ui + TanStack Query + Zustand + Tiptap | Tiptap 承载点评与文章富文本 |
| 实时 | **SSE**（`text/event-stream`） | 流式写作 + 检查进度，比 WebSocket 简单够用 |
| 部署 | Docker Compose（v1 单机） | 后续拆 k8s / 托管 PG |

> **关键取舍**：前端主体用 **React SPA**，不用 Astro。因为本产品是**登录后的强交互后台**（点评编辑器、检查 diff、流式写作、版本对比），没有 SEO 诉求，Astro 的岛屿架构只会增加心智负担。Astro 留给未来的「官网 / 文档站 / 公开内容站」单独仓库。

---

## 1. 文档导航

| 文档 | 内容 | 回答什么问题 |
| --- | --- | --- |
| [`01-product-plan.md`](./01-product-plan.md) | **产品方案** | 做什么、为什么这么做、Agent 形态、功能模块、MVP 与路线图 |
| [`02-audience.md`](./02-audience.md) | **受众分析** | 卖给谁、他们的痛点与付费意愿、优先级排序 |
| [`03-user-flow.md`](./03-user-flow.md) | **使用流程** | 用户从打开网页到成文的完整路径、状态机、异常分支 |
| [`04-architecture.md`](./04-architecture.md) | **技术架构** | 分层设计、数据源抽象层、Agent 编排、API、前端方案 |
| [`05-database-schema.md`](./05-database-schema.md) | **数据库表结构** | 36 张表的完整 DDL、ER 图、索引与分层策略 |

建议阅读顺序：`01 → 02 → 03`（产品侧）→ `04 → 05`（工程侧）。

---

## 2. 核心设计原则（贯穿全部文档）

1. **观点是燃料，AI 是引擎** — 产品不替用户"想"，只帮用户"说清楚"。用户必须留下点评，系统才产出。
2. **事实与观点分离** — 任何一个句子在系统里都有归属：`fact`（可验证）或 `opinion`（用户判断）。写作时分别对待，事实必须带证据，观点必须归属到人。
3. **HITL（Human-in-the-loop）是主线不是补丁** — 每个关键节点都允许"暂停 → 用户看 → 用户改 → 继续"，靠 LangGraph 的 `interrupt()` + checkpointer 实现。
4. **一切可追溯** — 文章里的每一段都能回溯到「哪条资讯 + 哪条点评 + 哪个提示词版本 + 哪次 run」。
5. **数据源必须可插拔** — 今天 tushare，明天 RSS / 公众号 / 雪球 / 交易所 / 板块行情。抽象层设计见 `04-architecture.md` §4。
6. **风格克隆靠"提示词资产化"** — 用户的提示词不是一串字符，是一份可版本化、可复用、可加载进 Agent 的**技能包**。
7. **可规模化的部分必须复用，不能每次重算** — 事实基线在 ingest 阶段按资讯预生成并跨用户复用；embedding / 报告按内容哈希缓存。这条同时决定了延迟与成本能否达标。
8. **SaaS 与私有化共用一套代码** — LLM / Embedding / 可观测 / 凭据全部走 `ModelProvider` / `Tracer` / `SecretsProvider` 抽象。券商客户（P0）要求数据不出域，这个约束从第一行代码起就存在。

---

## 3. 里程碑速览

| 阶段 | 目标 | 交付 |
| --- | --- | --- |
| **M0 · 假设验证**（3~5 天，零代码） | 验证"用户愿意先写点评" | 20 个种子用户 Wizard-of-Oz；不达标不进 M1 |
| **M1 · 数据底座**（2 周） | 资讯能进来、能看 | tushare connector + 统一模型 + 资讯流页面 + 收藏/评级 |
| **M2 · 观点闭环**（3 周） | 点评能写、能查 | 点评编辑器 + ReviewerAgent 三轨检查 + 结构化报告 + 迭代修订 |
| **M3 · 自动写作**（3 周） | 文章能出 | 提示词管理 + WriterAgent（DeepAgent）+ 流式写作 + 版本对比 + 导出 |
| **M4 · 沉淀与扩展**（持续） | 越用越懂你 | 观点库、风格记忆、第二数据源接入、多平台改写、发布对接 |

详细拆解见 `01-product-plan.md` §7。
