# TODO · 主理人 Agent

> 状态：**M1 · 数据底座 —— 后端真机链路跑通，前端资讯流页面已交付**
> 最后更新：2026-09-19
> 相关文档：`docs/01`~`docs/05`

---

## 0. 已完成（供对照）

| 项 | 状态 |
| --- | --- |
| uv + Python 3.12 + FastAPI + SQLAlchemy 2.0 async 骨架 | ✅ |
| 数据源抽象层（Protocol + Registry + `@register`） | ✅ |
| TushareConnector（含权限探测、限流、分段续拉） | ✅ |
| ODS/DWD 两级落库 + 跨源去重（追加来源而非丢弃） | ✅ |
| 16 张表 + 2 个迁移（结构 / 触发器） | ✅ |
| arq worker（sync / enrich + cron） | ✅ |
| 资讯与数据源 REST API | ✅ |
| 真机同步验证（fetched 1628 / inserted 1578 / duplicated 50） | ✅ |
| ruff + pytest | ✅ 通过 |
| **前端资讯流页面**（`apps/web`：收件箱 / 资讯流 / 详情 / 数据源管理） | ✅ |
| 前端 `tsc --noEmit` + `vite build` | ✅ 通过 |
| 前后端联通（Vite 代理 `/api` → 8000 返回真实数据） | ✅ 验证 |

---

## P0 · 阻塞项（不解决会带病进 M2）

### 1. 事件簇没有真正聚起来 ⭐ 最关键

- **现象**：1579 条资讯 → 1574 个簇，几乎一对一。"事件簇折叠 / 另有 N 家报道 / 展开看各源差异"实际不可用。
- **原因**：`NewsRepository._assign_cluster` 用的是规则版 simhash，阈值汉明距离 ≤ 3 过严。
- **影响**：直接吃掉「多源交叉验证」这个产品卖点。
- **做法**：
  - [ ] 先用真实样本调阈值（试 5 / 8 / 10），统计「误聚率」与「漏聚率」，选平衡点
  - [ ] 引入 embedding 余弦相似度替代/补充 simhash（注意：当前 2048 维暂无法建 HNSW，见 P0-2）
  - [ ] 长期：由 `ScoutAgent`（ingest_graph）做模型判定，表结构不变，只替换 `_assign_cluster`
- **验收**：同一事件的多个来源应落到同一 `cluster_id`，`source_count` ≥ 2 的簇占比 > 10%

### 2. pgvector 索引维度超限

- **现象**：环境 `EMBEDDING_DIM=2048`（volcengine doubao-embedding-vision），
  而 pgvector 的 HNSW / IVFFlat **最多 2000 维**，建索引直接报错。
- **现状**：迁移里做了条件化创建（>2000 时不建索引，走全表扫描）。
- **做法**：
  - [ ] 决定向量方案：① 换 ≤2000 维的模型；② Matryoshka/PCA 降到 1024~1536 再入库；③ 维持全表扫描（仅小数据量可行）
  - [ ] 定案后**固定** `EMBEDDING_DIM`，并在文档中更新（当前文档仍写 1024）
  - [ ] 清理技术债：`DIM > 2000` 时 `alembic autogenerate` 会反复检出索引差异（模型声明了索引、库里没有）
- **验收**：`ix_news_items_embedding` 存在且语义检索走索引

### 3. tushare 接口权限不足（Spike #1 结论）

| 接口 | 实测 | 后果 |
| --- | --- | --- |
| `news`（快讯） | 返回 0 行、**不报错** | 最危险，会造成"同步成功但 0 条"假象 |
| `anns_d` / `npr` / `research_report` | 无权限 | **公告 / 政策 / 研报三类素材拿不到** |
| `major_news` / `cctv_news` / 行情类 | 可用 | — |

- **做法**：
  - [ ] 评估换更高积分 token 的成本
  - [ ] 或接第二数据源补缺口（RSS / 交易所公告 / 政府网政策），这也正是"数据源可插拔"的意义
  - [ ] 前端展示 `source_connectors.config.probe`，明确告知"当前 token 无 XX 接口权限"
- **验收**：至少能覆盖「快讯 + 公告 + 政策」三类 content_type

---

## P1 · M1 收尾

### 4. ✅ 前端资讯流页面（M1 交付项，已完成 2026-09-19）

**已实现**（`apps/web`，React 19 + Vite 6 + TS + Tailwind v4 + TanStack Query）：

| 能力 | 说明 |
| --- | --- |
| `/` 今日收件箱 | 取今日资讯，前端按 `importance` 降序 |
| `/news` 资讯流 | 时间范围 / 类型 / 行业筛选 + 无限滚动分页（50/页） |
| `/news/:id` 整页详情 | 全文、原文链接、**簇内其他报道**、来源登记 |
| 详情抽屉 | 点卡片即开，`Esc` 关闭，不打断浏览 |
| 快捷键 | `j/k` 移动、`s` 收藏、`1~5` 评级、`space` 选中 |
| 卡片徽标 | 重要度三档（重要/一般/参考）、内容类型、行业、**「另有 N 家报道」** |
| 批量选中 | 底部浮层计数（"写点评"按钮禁用，留待 M2） |
| `/settings/connectors` | 创建 / 校验 / 同步 / 删除 + **接口权限探测结果可视化** |
| 乐观更新 | 收藏与评级即时反馈，失败回滚 + Toast |

**与 `docs/04 §8.2` 选型的偏差（有意选择，降低配置复杂度）**：

| 文档选型 | 实际 | 原因 |
| --- | --- | --- |
| TanStack Router | `react-router-dom` v7 | 免去 routeTree 代码生成；后续可平滑迁移 |
| shadcn/ui + Radix | 手写基础组件（`ui.tsx`） | M1 只需 Badge/Button 等少量组件，避免 CLI 生成大量文件 |
| TanStack Virtual 虚拟滚动 | `useInfiniteQuery` + IntersectionObserver | 当前 1.5k 条量级分页足够；**超过 1 万条再换虚拟列表** |
| Zustand | 未引入 | 选中态/光标用 `useState` 已足够 |
| Tiptap | 未引入 | M2 点评编辑器才需要 |

**验证**：`tsc --noEmit` + `vite build` 通过；Vite 代理 `/api` → `:8000` 返回真实数据；SPA 首页与 `/news/:id` 均 200。

### 5. 同步指标未达标

- **现象**：重复率 **3%**（50/1628），M1 验收要求 **< 2%**
- **做法**：随 P0-1 归簇/去重改进一起解决

### 6. M0 假设验证（未执行）

- [ ] 20 个种子主理人 Wizard-of-Oz：愿不愿意写点评？一次写几条？建议采纳率能到 50% 吗？
- [ ] 打字 vs 语音碎片转写（影响 M2 编辑器形态）
- **这是进 M2 前的 Gate**，零代码，3~5 天

### 7. 鉴权未接

- **现状**：`X-User-Id` 头 + dev 默认用户（`00000000-...-0001`），无 JWT / 无租户隔离
- [ ] 接入 JWT（含 refresh）
- [ ] 所有面向用户的查询强制 `user_id` 过滤；团队版启用 RLS
- [ ] `users.org_id` / `projects.org_id` 已预留，接多租户时补 `orgs` 表

---

## P2 · 已知技术债

### 8. 配额与成本硬上限未实现

- **现状**：`usage_records` 表已建，但无累计逻辑、无硬上限
- [ ] 按 run 累计 token 与费用写入 `usage_records`
- [ ] 超额**直接拒绝**（不是软提示）—— 评审指出 ¥199/月"无限写作"存在亏损风险
- [ ] 单次 compose 成本实测（Spike #7），回填定价模型

### 9. 向量与检索能力未接入

- [ ] embedding 计算未实现（列已建，值为 NULL）
- [ ] 混合检索（向量 + 关键词）未实现；v1 中文检索靠 `pg_trgm(title)`，`zhparser` 未装
- [ ] `POST /news/search`（方案里的语义 + 关键词混合检索）未实现

### 10. Agent 层尚未开始

- [ ] `ScoutAgent`（ingest_graph）—— 替换规则版打标与归簇
- [ ] `ResearcherAgent` + `web_probe`（网页检索，tushare 覆盖不到的海外/自由文本源）
- [ ] `ReviewerAgent` 三轨（fact / logic / compliance）—— 注意三轨阈值必须分开
- [ ] `WriterAgent`（deepagents）—— **先 Spike 验证 `skills` 参数形态**，可能阻塞 M3
- [ ] LangGraph `interrupt` + Postgres checkpointer 端到端验证（Spike #2，核心体验）

### 11. 实时与可观测

- [ ] SSE 未实现；`stream_events` 表未建
  - 约定：只落**里程碑事件**，token delta 走 Redis pub/sub，不写库
- [ ] LangSmith / Langfuse trace 未接入
- [ ] Prometheus 指标未接入

### 12. 工程化

- [ ] `docker-compose.yml` 缺 `api` / `worker` 服务（当前只有 pg / redis / minio）
- [ ] 无 CI（ruff + pytest + alembic check）
- [ ] 无 seed 数据 / 官方提示词模板库
- [ ] `enrich_service` 是规则版（行业关键词表），待 ScoutAgent 替换
- [ ] 私有化抽象的 `ModelProvider` / `Tracer` / `SecretsProvider` 尚未落到代码（目前直接用 tushare / structlog）

---

### 13. 前端遗留（M1 未覆盖）

**未做的页面**（文档 `04 §8.3` 已列出，均在 M2/M3）：

- [ ] `/settings/interests` 兴趣画像（后端 `user_interests` 已有，无 API）
- [ ] 观点室（点评工作台 + 体检报告）—— M2
- [ ] 写作台 / 稿件库 / 用量看板 / 风格画像 —— M3/M4

**已知缺口**：

- [ ] **收件箱是简化版**：后端 `GET /news/inbox`（兴趣召回）未实现，前端用 `since=今日` + 前端按重要度排序代替
- [ ] 卡片缺少「隐藏 / 屏蔽同类」按钮（后端 `hide` / `block_source` 已支持）
- [ ] 详情缺「关联标的」「行情小图」（后端详情未返回 symbols，需补 `news_item_symbols` 查询）
- [ ] 无错误边界组件（文档 `04 §8.4` 要求"Agent 任务失败要显示哪一步失败，不要白屏"）
- [ ] 无登录页 / 用户切换（后端鉴权未接，见 P1-7）
- [ ] 无草稿本地兜底（`localStorage`）—— M2 点评编辑器才需要
- [ ] SSE 未接（M2 检查进度与流式写作才需要）

**测试与指标**：

- [ ] 无 E2E（Playwright）与组件测试（Vitest）—— 文档 `04 §8.2` 已列入选型
- [ ] M1 验收「页面响应 < 300ms」未实测
- [ ] M1 验收「连续 3 天自动同步」未验证（arq cron 已配置，但未长跑）

---

## 附：如何复现当前验证

```bash
cd infra && docker compose up -d postgres redis     # pg 5433 / redis 6380
cd ../apps/api
uv sync && cp .env.example .env
uv run alembic upgrade head
uv run pytest tests/ -q          # 5 passed
uv run uvicorn app.main:app --reload
uv run arq app.workers.settings.WorkerSettings
```

前端：

```bash
cd apps/web
npm install
npm run dev        # http://localhost:5173，/api 已代理到 :8000
npm run build      # tsc --noEmit && vite build
```

> Postgres 用 5433、Redis 用 6380 是为了避开本地已占用的 5432 / 6379。
> 前后端需同时启动：`uvicorn`（:8000）+ `vite`（:5173）。
