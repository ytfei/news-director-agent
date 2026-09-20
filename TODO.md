# TODO · 主理人 Agent

> 状态：**M1 ✅ 数据底座 · M2 ✅ 素材 / 批注 / 体检 / 选题（检查为规则版）**
> 最后更新：2026-09-20
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
| `/settings/connectors` | 数据源 | 权限探测、手动同步、同步日志 |

### 1.4 验收口径（可复现）

```bash
cd apps/api
uv run alembic upgrade head          # 0001 → 0004
uv run pytest tests/ -q              # 18 passed
uv run ruff check app                # All checks passed
uv run alembic check                 # 仅剩已知的 pgvector 索引差异（P0-2）

cd ../web
npm run build                        # tsc --noEmit + vite build 通过
```

- 规则单测（8 条，无需 DB）：三轨严重度取向、verdict 派生、驳回过的不再拦截
- M2 集成测试（5 条，走真库）：幂等标记素材 → 主题筛选 → 批注版本 → 检查出 blocker → 红线未处置时 compose 返回 409 → 采纳/驳回 → 复检 → 可写作 → 触发写作；「无点评素材直接写作（digest 模式）」；无批注时检查返回 422；系统主题与统计；官方提示词已 seed
- M1 冒烟（5 条）：注册表 / 标准码 / 归一化纯函数 / health + available，以及一条**真机 tushare 同步**（依赖 `.env` 里的 `TUSHARE_TOKEN`，缺失时会 skip —— 注意 skip 与 pass 的区别）

---

## 2. 本次交付暴露的问题

### 2.1 已修复

| # | 现象 | 根因 | 处置 |
| --- | --- | --- | --- |
| D1 | 保存素材/批注后报 `MissingGreenlet` | `server_default` 与 `onupdate=func.now()` 的字段在 `flush` 后未回读，异步下隐式 IO | 仓储层写后统一 `refresh`；测试与注释固化该约定 |
| D2 | 触发写作时 `Object of type UUID is not JSON serializable` | `agent_runs.input` 里塞了 UUID 对象（只在真正 compose 时才暴露） | JSONB 落库前统一 `str()` |
| D3 | **集成测试被静默 skip，假装通过** | `engine` 是模块级，pytest-asyncio 每测试一个事件循环，跨循环复用 asyncpg 连接 | 新增 `tests/conftest.py` 每测试后 `engine.dispose()` |
| D4 | 素材主题从零开始打，跨日期无聚类价值 | 未预置主题词表 | 迁移 0004 预置 15 个系统主题 |

> D3 最危险：`pytest` 报"通过"，但 4 条集成测试其实一条都没跑。修掉后立刻暴露了 D2 与 D4。

### 2.2 待修（已定位，进入 M2 收尾）

| # | 现象 | 影响 | 方向 |
| --- | --- | --- | --- |
| D5 | 采纳建议 / 改写正文后，旧报告的 `span_start/span_end` 会错位 | 体检页高亮画错位置 | 报告增加 `is_stale` 标记（版本号 ≠ 当前版本即提示"报告已过期，请复检"） |
| D6 | 驳回记忆永久化：正文大改后仍屏蔽同一问题 | 用户改了写法却拿不到新结论 | 正文变更超过阈值（如 diff > 30%）时清空该点评的驳回记忆 |
| D7 | 前端用 `window.location.href` 跳转 | 绕过 react-router，丢失 SPA 状态 | 统一改 `useNavigate` |
| D8 | 单批检查上限 20 / 并发 ≤5 只在文档 | 批量提交可能打满 LLM 造成成本尖峰 | 服务端 enforce + 返回 429/422 |
| D9 | `/materials` 用 `limit/offset`，无游标 | 素材上量后翻页退化 | 改用 `before_date + offset` 复合游标 |
| D10 | 集成测试写进开发库 | 开发库被测试数据污染（当前 18 条测试素材） | 独立测试库 + `seed` / `reset` 脚本 |

---

## 3. P0 · 阻塞（不解决会带病进 M3）

### 1. ★ 事件簇没有真正聚起来

- **现象**：1579 条资讯 → 1574 个簇，几乎一对一，"另有 N 家报道 / 展开看各源差异"不可用。
- **原因**：`NewsRepository._assign_cluster` 用规则版 simhash，汉明距离 ≤ 3 过严。
- **影响**：直接吃掉「多源交叉验证」这个产品卖点；**前端资讯中心的事件簇 UI 目前只能按理想态展示**。
- [ ] 用真实样本调阈值（5 / 8 / 10），统计误聚率与漏聚率
- [ ] 引入 embedding 余弦相似度（注意 2048 维暂不能建 HNSW，见 P0-2）
- [ ] 长期：由 `ScoutAgent` 做模型判定，表结构不变，只替换 `_assign_cluster`
- **验收**：`source_count ≥ 2` 的簇占比 > 10%

### 2. pgvector 索引维度超限

- **现象**：`EMBEDDING_DIM=2048` > HNSW / IVFFlat 上限 2000，建索引报错；迁移里条件化跳过。
- **现状**：`alembic check` 会反复检出 `ix_news_clusters_centroid` / `ix_news_items_embedding` 差异 —— **这是当前 CI 的门槛问题**。
- [ ] 定案向量方案（换 ≤2000 维模型 / Matryoshka 降维 / 维持全表扫描）
- [ ] 固定 `EMBEDDING_DIM` 并更新文档（文档仍写 1024）
- **验收**：`alembic check` 无差异，语义检索走索引

### 3. tushare 接口权限不足

| 接口 | 实测 | 后果 |
| --- | --- | --- |
| `news`（快讯） | 返回 0 行、**不报错** | 最危险，会造成"同步成功但 0 条"假象 |
| `anns_d` / `npr` / `research_report` | 无权限 | 公告 / 政策 / 研报三类素材拿不到 |
| `major_news` / `cctv_news` / 行情类 | 可用 | — |

- [ ] 评估更高积分 token 成本，或接第二数据源（RSS / 交易所公告 / 政府网政策）
- [ ] 前端展示 `source_connectors.config.probe`，明确告知"当前 token 无 XX 接口权限"
- **验收**：至少覆盖「快讯 + 公告 + 政策」三类 `content_type`

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

- [ ] D5 报告过期提示、D6 驳回记忆失效策略、D7 路由跳转、D8 批量上限 enforce、D9 素材分页游标
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

### 15. 工程化（一直欠着）
- [ ] `docker-compose.yml` 补 `api` / `worker` 服务（当前只有 pg / redis / minio）
- [ ] CI：ruff + pytest + `alembic check`（**先解 P0-2，否则 check 必然红**）
- [ ] 测试库隔离 + `seed` / `reset` 脚本（解 D10）
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
# 1. 基础设施（pg 5433 / redis 6380 / minio）
cd infra && docker compose up -d postgres redis

# 2. 后端
cd ../apps/api
uv sync && cp .env.example .env
uv run alembic upgrade head        # 0001 → 0004
uv run pytest tests/ -q            # 18 passed
uv run uvicorn app.main:app --reload --port 8000
uv run arq app.workers.settings.WorkerSettings

# 3. 前端（dev server 代理 /api → :8000）
cd ../web && npm install && npm run dev   # http://localhost:5173

# 4. 看交互设计（纯静态，无需后端）
open prototype/index.html
```

> Postgres 用 5433、Redis 用 6380 是为了避开本地已占用的 5432 / 6379。
> 迁移链：`c6fca63ba48f`（M1 核心 16 表）→ `0002_triggers` → `0003_materials`（M2 中枢 14 表）→ `0004_system_topics`（预置主题）。
