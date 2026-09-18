# 主理人 Agent · API

观点驱动的内容生产工作台后端（FastAPI + SQLAlchemy 2.0 async + Alembic）。

当前进度：**M1 · 数据底座**。

## 快速开始

```bash
# 1. 依赖
uv sync

# 2. 起基础设施（Postgres + pgvector / Redis）
docker compose -f ../../infra/docker-compose.yml up -d

# 3. 迁移
cp .env.example .env
uv run alembic upgrade head

# 4. 起服务
uv run uvicorn app.main:app --reload --port 8000

# 5. 起 worker（同步 / 打标）
uv run arq app.workers.settings.WorkerSettings
```

## 目录

```
app/
├── core/          配置 / 日志 / DB / Redis
├── api/v1/        路由（thin controllers）
├── connectors/    ★ 数据源接入层（Protocol + Registry + tushare）
├── repositories/  数据访问
├── services/      领域服务（事务边界）
├── workers/       arq 任务
├── models/        SQLAlchemy 模型
└── lib/           去重 / 哈希 / 加密
```

## 关键约定

- 新增数据源 = 新增一个文件 + `@register`，不改调度器 / API / 前端
- `raw_documents` 是 ODS 原始层，永不覆盖；归一化规则可重放
- 跨源命中 `content_hash` 时**追加来源**，绝不丢弃（否则多源交叉验证失效）
- 凭据只存加密引用（`source_connectors.credentials_ref`）
