# 主理人 Agent · API

观点驱动的内容生产工作台后端（FastAPI + SQLAlchemy 2.0 async + Alembic）。

当前进度：**M2 · 素材 → 批注 → 体检 → 选题（检查为规则版）**。

## 快速开始

推荐用仓库根的 Makefile（`make` 可列出全部命令）：

```bash
make env          # 生成 .env
make infra        # 起 pg 5433 / redis 6380 / minio
make install      # uv sync
make migrate      # alembic upgrade head
make doctor       # 自检：配置 / 连接 / 迁移版本 / 向量维度一致性
make dev-api      # :8000（另开终端跑 make dev-worker）
```

手动等价命令：

```bash
uv sync
docker compose -f ../../infra/docker-compose.yml up -d postgres redis
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
uv run arq app.workers.settings.WorkerSettings
```

容器化部署（api / worker / migrate 共用 `apps/api/Dockerfile` 一个镜像）：

```bash
make up           # 全套 → web :8080 / api :8000
make logs-api
make sh-api       # 进容器
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
