# 07 · 代码评估指南（Code Review Guide）

> 面向**做代码评估的人**：按本文件逐条走，能在 1~2 天内覆盖架构、核心流程、数据模型、
> 大模型与提示词、监控埋点、稳定性与性能七个面。
>
> 每个检查点都给出「看什么 / 判定标准 / 风险等级」。风险等级含义：
> 🔴 阻塞（不解决不该上线）· 🟡 需关注（影响质量或成本）· 🟢 建议（优化项）
>
> 文中「已确认」= 本次评估已实测过的事实；「待核实」= 需要你亲自看代码确认的点。

---

## 0. 评估路线（建议顺序）

| 阶段 | 内容 | 预计 | 产出 |
| --- | --- | --- | --- |
| 1 | 跑通环境 + 读 §1 架构地图 | 1h | 确认分层是否守住 |
| 2 | 跟两条主链路（§2）+ 数据流转（§3） | 3h | 画出你自己的流程图 |
| 3 | 数据库与索引（§4） | 2h | 索引/约束问题清单 |
| 4 | 大模型、提示词、埋点（§5~§7） | 2h | 成本与可观测缺口 |
| 5 | 稳定性与性能（§8~§9） | 2h | 风险清单 |
| 6 | 回填 §10 清单，出结论 | 1h | 放行 / 有条件放行 / 不放行 |

**先跑起来再读代码**：

```bash
make infra && make test-db-create && make doctor && make models
cd apps/api && uv run pytest tests/ -q --ignore=tests/test_smoke.py   # 应 90 passed
uv run python scripts/acceptance.py                                    # 看验收结论
uv run python scripts/compare_sources.py --hours 12                     # 多源对比
```

---

## 1. 架构地图

### 1.1 分层与边界（🔴 首要检查）

```
app/
├── api/v1/          路由层（thin controller）
├── services/        领域服务（事务边界、业务编排）
├── repositories/    数据访问（SQLAlchemy）
├── connectors/      数据源接入（Protocol + Registry + @register）
├── lib/             算法与工具（dedupe / hash / crypto）
├── models/          ORM 模型 + 枚举
├── workers/         arq 任务（sync / enrich / review）
└── scripts/         运维脚本（doctor / models / acceptance / backfill / compare_sources）
```

**判定标准**：
- `api/v1/*` 不应出现业务规则判断与直接 SQL（可以有参数校验与 DTO 转换）
- `services/*` 不应感知 FastAPI（无 `Request` / `Response`）
- `repositories/*` 不写业务规则，只做持久化
- Agent 层（尚未实现）届时不应直接持有 HTTP 上下文

**检查动作**：在 `api/v1/` 里搜 `select(` / `text(` / `SessionLocal`，出现即视为越界。

### 1.2 Connector 抽象（🟡）

- `connectors/base.py`：`DataSourceConnector` 协议、`RawItem`、`NormalizedItem`、`Provenance`、`ConfigField`
- `connectors/spec.py`：`ChannelSpec` + `FieldRef` —— **归一化规则是声明式的**（字段映射写在 spec 里，不在代码里）
- `connectors/registry.py`：`@register` 插件注册
- `connectors/tushare/`：base（限流/查询/时间处理）、specs（各接口的字段映射）、flash（快讯）、connector（文章等）

**判定标准**：新增一个数据源需要改几处？理想是「新增 1 个文件 + 注册」，**不改调度器、不改 API、不改前端**。
> 已确认：能力声明（`capability.config_schema`）驱动前端表单，新增渠道确实不需要改前端。

### 1.3 值得单独看的文件

| 文件 | 为什么重要 |
| --- | --- |
| `lib/dedupe.py` | 分层去重算法（归一化 / MinHash / 事件打分）—— 产品核心 |
| `repositories/news_repo.py` | 四层去重 + 归簇的落地，最容易出错的地方 |
| `services/sync_service.py` | 同步编排（锁、游标、失败段、统计） |
| `services/review_service.py` | 三轨检查（当前规则版） |
| `services/model_provider.py` | 模型层统一入口与档位路由 |
| `connectors/tushare/flash.py` | 多来源拉取（游标/限流/触顶细分/标题兜底） |

---

## 2. 核心流程

### 2.1 链路 A：资讯同步与归一化

```
arq cron / 手动触发
  → sync_service.run_sync(connector_id)
      ├─ SyncLock 获取（短 TTL + 心跳）
      ├─ sync_runs 建 run（status=running）
      ├─ validate()：凭据自检 + 逐来源探测
      └─ for raw in connector.fetch(cursor, window):
             ├─ raw_documents  upsert（ODS，canonical JSON hash 幂等）
             ├─ normalize()    → NormalizedItem（纯函数）
             └─ news_repo.upsert_draft()
                   ├─ L2 content_hash  → 命中则幂等登记来源
                   ├─ L3 MinHash       → 转载则合并，不新增条目
                   └─ L4 event_score   → 归簇（只比簇代表）
      → enrich_service（打标 + embedding，异步入队）
      → sync_runs 收尾（success / partial / failed + 分段失败明细）
```

**看代码顺序**：`sync_service.run_sync` → `flash.fetch` → `news_repo.upsert_draft` → `lib/dedupe`

**检查点**：

| # | 检查 | 判定 | 风险 |
| --- | --- | --- | --- |
| A1 | 游标按来源独立（`cursor.payload["srcs"]`） | 一个来源失败不应拖回其他来源 | 🔴 |
| A2 | 触顶（1500 条）是否二分区间 | 达到上限必须细分，不能静默丢 | 🔴 |
| A3 | 分段失败是否记入 `failed_segments` 且不推进游标 | 失败段下次要重拉 | 🟡 |
| A4 | 空结果是否给出人话原因（`empty_reason`） | 区分「无权限」与「区间无数据」 | 🟡 |
| A5 | 幂等：重复同步同一区间不产生脏数据 | 靠 external_id + content_hash + MinHash | 🔴 |

### 2.2 链路 B：观点闭环（M2）

```
素材标记（materials） → 批注（annotations/annotation_versions）
  → 提交检查（POST /annotations/check）
      → review_service：compliance / logic / fact 三轨（规则版）
      → review_reports + review_findings（含 span 定位）
  → 处置：采纳（改写正文并升版本）/ 驳回（必填理由，记忆不再重报）/ 忽略
  → 选题（projects + project_materials）
  → 触发写作（POST /projects/{id}/compose → 仅准入校验 + agent_runs 建档）
```

**检查点**：

| # | 检查 | 判定 | 风险 |
| --- | --- | --- | --- |
| B1 | `verdict` 由**未处置** finding 派生 | 处置后应实时变化 | 🟡 |
| B2 | blocker 未处置时 compose 返回 409 | 合规红线必须拦 | 🔴 |
| B3 | 采纳后正文改写并生成新版本 | `annotation_versions` 递增 | 🟡 |
| B4 | 驳回必填理由且同一问题不再重报 | 有驳回记忆 | 🟡 |
| B5 | 版本变更后旧报告的 span 是否失效 | 建议有 `is_stale` 提示（**待核实，TODO D8**） | 🟡 |

---

## 3. 数据模型流转

```
RawItem（渠道原始行：payload + channel）
   ↓ normalize()（声明式 spec，纯函数）
NormalizedItem（统一信封：external_id / title / content / source_name /
                symbols / entities / industries / provenance / attributes）
   ↓
raw_documents      ODS 原始留档（永不覆盖，可重放）
news_items         DWD 主表（去重 + 归簇 + 打标 + embedding）
market_facts       数值型事实（长表，一行一指标）
materials          用户标记的素材（关联 news_item）
annotations        批注（当前正文 + 版本号）
annotation_versions 批注版本快照（不可变）
review_reports / review_findings  体检报告与发现项
projects / project_materials      选题与素材组合
articles / article_versions       稿件（**M3 未产出**）
```

**关键约定（🔴 必查）**：
- `external_id` 与 `normalize` 必须用**同一套规则**（否则 ODS 与 DWD 对"同一条"判断不一致）
  → 见 `flash._fetch_segment` 的注释与实现
- 数值型条目可能没有 title → `display_title` 兜底（`news_items.title` 是 NOT NULL）
- 渠道身份要注入：上游返回没有 `src`，所以 `source_name` 来自 `$channel_label`

**检查点**：

| # | 检查 | 风险 |
| --- | --- | --- |
| C1 | 各阶段对象是否有清晰的 schema（Pydantic / dataclass） | 🟢 |
| C2 | 是否存在"半归一化"对象在层间传递（dict 满天飞） | 🟡 |
| C3 | `entities` / `keywords` / `industries` 由谁写入、是否真有值 | 🔴 见 §3.1 |

### 3.1 ⚠️ 实测发现（🔴）

**`entities` / `keywords` / `industries` 在 15982 条数据中无一有值**，embedding 只有 1 条。
原因：规则版 `enrich_service` 没有真正批量跑过，且只写 `industries`（还因为样本没命中关键词表而为空）。
**后果**：事件聚类只剩「标题重合 + 时间」两个信号，质量上限被锁死。

---

## 4. 数据库表结构

### 4.1 分组（32 张业务表）

| 组 | 表 |
| --- | --- |
| 采集 | `source_connectors` `raw_documents` `sync_runs` |
| 资讯 | `news_items` `news_clusters` `news_item_symbols` `news_item_relations` `tags` `news_item_tags` |
| 数值事实 | `market_facts` |
| 素材与批注 | `topics` `materials` `material_topics` `annotations` `annotation_versions` |
| 事实与体检 | `fact_cards` `fact_card_claims` `review_reports` `review_findings` |
| 选题与产出 | `projects` `project_materials` `prompt_templates` `articles` `article_versions` |
| Agent 与用量 | `agent_runs` `agent_steps` `usage_records` |
| 用户与通知 | `users` `user_interests` `user_news_actions` `notifications` |

### 4.2 设计约定（🟡 检查是否被执行）

- 主键统一 `uuid`，默认 `gen_random_uuid()`
- 时间统一 `timestamptz`
- 软删除 `deleted_at`
- **唯一性一律用部分唯一索引**，不把 `deleted_at` 放进 `UNIQUE`
  > 已确认：`source_connectors`、`prompt_templates` 都是部分唯一索引（含"平台级 user_id IS NULL"分支）
- `updated_at` 由触发器维护（迁移 0002）+ ORM `onupdate` 兜底

### 4.3 索引与性能（🔴 重点）

| # | 检查 | 现状 |
| --- | --- | --- |
| D1 | 向量索引是否存在 | ✅ **已建**（2026-09-28）：Matryoshka 降至 1024 维后建成 HNSW（迁移 0008），检索 O(log n)。**存量向量仍待补跑**（覆盖 0.0%） |
| D2 | `news_items` 的 GIN 索引 | 有（industries / keywords / entities / market_scope / title trgm） |
| D3 | 分页是否游标式 | `/materials` 用 limit/offset（**待改进，TODO D12**） |
| D4 | 列表查询是否有 N+1 | `projects` 列表带扁平统计（已规避）；**其他列表待核实** |
| D5 | `source_refs` 数组膨胀 | 历史上不幂等导致长度达 39；**已修**（按来源名判重）+ 存量已清理（均值 2.38） |

### 4.4 迁移链

```
c6fca63ba48f (M1 核心) → 0002_triggers → 0003_materials
  → 0004_system_topics → 0005_market_facts
  → 0006_ensure_extensions → 0007_dedupe_fields
```

**检查点**：
- `alembic check` 应无差异（已确认通过）
- 扩展在 `env.py` 的 `ensure_extensions()` 里建（**在所有迁移之前**，否则新建库会失败）
  > 已确认：曾出现"迁移全部 Running 成功但库里 0 张表"的静默回滚（D17），根因是在
  > `begin_transaction()` 之前用同一连接执行 DDL。务必确认这个坑没有复发。

---

## 5. 大模型使用

### 5.1 档位与路由（`services/model_provider.py`）

| 档 | 模型 | 定位 |
| --- | --- | --- |
| `pro` | `doubao-seed-2.1-pro` | 旗舰深度推理（1M） |
| `turbo` | `doubao-seed-2.1-turbo` | 均衡主力（256k，**默认档**） |
| `lite` | `doubao-seed-2.1-lite` | 轻量批量（256k） |

场景 → 档位（`DEFAULT_TIER`）：

| Task | 档位 |
| --- | --- |
| `classify` / `extract` / `title` | turbo |
| `summarize` / `fact_check` | lite |
| `review` / `write_section` / `style` | turbo |
| `write_plan` | **pro** |

### 5.2 实测成本与延迟（🟡 已确认）

| 任务 | pro | turbo | lite |
| --- | --- | --- | --- |
| 简单分类 | 194 tok / 6.5s | **36 tok / 2.1s** | 407 tok / 8.9s |
| 事实核查 | 4285 tok / 108s | 3613 tok / 56s | 3055 tok / 48s |

三点结论：
1. 三款**都是推理模型**（reasoning 占 97~100%）
2. turbo 是甜点
3. **lite 并不比 turbo 省**（"轻量"是能力定位，不是思考更少）

### 5.3 当前实际调用点（🔴 关键缺口）

**只有一处**：`enrich_service.llm_tag`（分类），且默认 `ENRICH_USE_LLM=False`。

即：**目前线上没有任何模型调用在跑**。检查引擎是规则版（`rules-v1`），写作是占位。

**检查点**：

| # | 检查 | 判定 | 风险 |
| --- | --- | --- | --- |
| E1 | `ModelProvider` 是否所有调用的唯一入口 | 不应有裸 SDK 调用 | 🔴 |
| E2 | 无 key 时是否降级不崩溃 | `enabled=False` 且调用方有兜底 | 🔴 |
| E3 | reasoning token 是否单独统计 | `TokenUsage.reasoning` | 🟡 |
| E4 | 深度检查/写作是否已异步化 | **核查超时 48~108s，同步等待必然超时** | 🔴 |
| E5 | 是否有超时与重试 | `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | 🟡 |

---

## 6. 提示词

### 6.1 现状（🔴 关键缺口）

- 表 `prompt_templates` 已建，官方模板已 seed（4 套），前端有管理页
- **但这些提示词目前没有被任何模型调用使用** —— 因为写作（M3）未实现
- 唯一在代码里的 prompt 是 `enrich_service.llm_tag` 的 system 提示（分类任务）

### 6.2 检查点

| # | 检查 | 风险 |
| --- | --- | --- |
| F1 | 提示词是否版本化、可回滚 | 🟡（表有 `version_no`，回滚 UI 待核实） |
| F2 | 是否有 prompt 变更的评测回归 | 🔴 无（需标注集） |
| F3 | 提示词是否拼进 Agent 而不污染上下文 | 🟢（M3 待设计：Skill 包按需加载） |
| F4 | 用户提示词是否有注入风险 | 🟡（用户输入进 prompt，需边界） |

---

## 7. 监控埋点

### 7.1 有什么（🟢）

- `structlog` 结构化日志：关键服务都有 `log.info/warning`，含 `connector_id` / `run_id` / `src` 等字段
- `sync_runs`：每次同步的 fetched / inserted / duplicated / failed_segments / 耗时
- `agent_runs`：Agent 执行记录（含 model、token、status、interrupt_payload）
- 运维自检三件套：`make doctor`（配置/DB/Redis/迁移/向量一致性）、`make models`（模型连通）、`make acceptance`（验收指标）
- worker 健康：arq 自带 health-check beacon（compose 里读该 key）

### 7.2 缺什么（🔴）

| 缺口 | 说明 |
| --- | --- |
| **成本累计未实现** | `usage_records` 表已建，但**代码里没有任何写入**（已确认：仅 models 引用）→ 无法知道花了多少钱 |
| **步骤级 trace 未实现** | `agent_steps` 表已建，无写入 |
| **无指标系统** | 无 Prometheus / 无告警；只有日志 |
| **无配额硬上限** | 文档写了并发 ≤5，但服务端未 enforce（TODO D11） |
| **无 trace 接入** | LangSmith / Langfuse 均未接 |

### 7.3 检查点

| # | 检查 | 风险 |
| --- | --- | --- |
| G1 | 一次请求能否用 `request_id` / `run_id` 串起全链路日志 | 🟡 |
| G2 | 模型调用是否都有 token 与耗时日志 | 🟡 |
| G3 | 成本是否可归因到用户 / 任务 | 🔴 |
| G4 | 失败是否有可观测信号（非仅日志） | 🟡 |

---

## 8. 稳定性

| 机制 | 实现 | 检查点 |
| --- | --- | --- |
| 并发互斥 | `SyncLock`：短 TTL(300s) + 心跳续约 + token 安全释放（**已修 D21**） | 崩溃后能否自动恢复；长任务是否丢锁 |
| 限流 | connector 内 token bucket（tushare 按来源限流） | 是否真的生效 |
| 增量游标 | 按来源独立，段成功后才推进 | 失败段是否重拉 |
| 失败处理 | 分段失败记录 + 不推进游标；`status=partial` | 部分失败是否被吞 |
| 降级 | 模型不可用 → 规则结果照常入库 | 是否真的不崩 |
| 数据兜底 | title 缺失从正文提取（**已修 D18**） | 幂等键是否还会撞车 |
| 时区 | 连接器入口统一（**已修 D19**） | 是否还有 naive/aware 混用 |

**重点核查（🔴）**：
1. 同步中途 kill 进程 → 锁是否在 300s 内释放、游标是否停在上一段（可重拉）
2. 某个来源无权限 → 其他来源是否照常完成
3. 上游返回脏值（NaN）→ 是否有 `json_safe` 处理（已确认有）

---

## 9. 性能

| # | 关注点 | 现状 / 建议 |
| --- | --- | --- |
| H1 | 归簇复杂度 | 只与**簇代表**比较（`is_cluster_rep`），非全表——**确认这条没退化** |
| H2 | 转载判定候选 | 用 `minhash_bucket` 粗筛（简化 LSH），限制候选 200 |
| H3 | MinHash 计算量 | 文本截断到 1000 字符（`dedupe_text`），避免长正文拖慢 |
| H4 | 批量写入 | 同步每 50 条 commit 一次 |
| H5 | embedding 批量 | `EMBEDDING_BATCH_SIZE=32` + 并发 2 |
| H6 | 列表分页 | `/materials` 仍是 offset（数据量大后退化） |
| H7 | 向量检索 | ✅ HNSW 已建（1024 维，迁移 0008）；**存量向量待补跑**（当前覆盖 0.0%） |
| H8 | 前端 | 无限滚动（50/页），未上虚拟列表（万级再换） |

---

## 10. 评估清单（可直接勾选）

### 架构
- [ ] 分层边界无越界（API 无 SQL、Service 无 HTTP）
- [ ] 新增数据源只需加文件 + 注册
- [ ] 归一化规则声明式（spec）而非散落 if-else

### 流程与数据
- [ ] 同步幂等（重复跑不产生脏数据）
- [ ] 游标/失败段/触顶细分正确
- [ ] 四层去重（精确 / 转载 / 事件）语义清晰且**分开实现**
- [ ] `entities` / `keywords` 有值（**当前为空 → 待补**）
- [ ] 数据流转各阶段对象 schema 明确

### 数据库
- [ ] `alembic check` 无差异
- [ ] 新建库能直接 `upgrade head`（扩展已前置）
- [ ] 部分唯一索引写法正确
- [ ] 无 N+1；分页游标化

### 模型与提示词
- [ ] 模型调用唯一入口 `ModelProvider`
- [ ] 无 key 降级不崩
- [ ] **深度检查/写作异步化**（当前同步会超时）
- [ ] 提示词有版本、有评测回归

### 监控
- [ ] 成本可归因（`usage_records` 写入）
- [ ] 关键链路可用 run_id 串联
- [ ] 有失败告警而非仅日志

### 稳定性与性能
- [ ] 锁崩溃可恢复
- [ ] 限流生效
- [ ] 归簇/去重不退化成全表比较

---

## 11. 已知问题索引（供对照，避免重复发现）

| 编号 | 主题 | 状态 |
| --- | --- | --- |
| D1 | 异步下 `server_default` 字段未回读（`MissingGreenlet`） | 已修 |
| D2 | `agent_runs.input` 塞 UUID 导致序列化失败 | 已修 |
| D3 | **集成测试被静默 skip 假装通过** | 已修（conftest 每测试 dispose engine） |
| D8 | 版本变更后旧报告 span 错位 | 待修 |
| D9 | 驳回记忆永久化 | 待修 |
| D11 | 批量检查并发上限未 enforce | 待修 |
| D12 | `/materials` 未游标化 | 待修 |
| D13 | 测试写开发库 | 已修（独立 `nda_test` + `make test-db-create`） |
| D16 | 新建库迁移失败（缺扩展） | 已修（`env.py` 前置 + 迁移 0006） |
| D17 | 迁移静默回滚（0 张表） | 已修（独立连接 + commit） |
| D18 | 新浪/华尔街见闻 title 为 None → 幂等键撞车 | 已修（`title_from_content`） |
| D19 | naive/aware 时区混用 | 已修（`ensure_tz`） |
| D20 | `source_refs` 追加不幂等（长度 39） | 已修（按来源名判重）+ 存量清理 |
| D21 | 同步锁 TTL 3600s 过长 | 已修（300s + 心跳 + token） |

**顶层待决策**（不在代码层，需业务判断）：
1. 是否补实体抽取与 embedding（决定事件聚类上限）
2. 是否建标注集标定阈值（决定 0.32 是否有依据）
3. 鉴权何时接（决定能否给外部使用）
4. 成本与定价：需先有 `usage_records` 累计
