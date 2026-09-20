# ============================================================================
# 主理人 Agent · 开发 / 构建 / 部署入口
#
#   make            # 列出全部命令
#   make doctor     # 先跑这个：配置 → 连接 → 迁移版本 → 向量维度一致性
#
# 两套运行模式，互不干扰（端口不冲突，可同时存在）：
#   A. 本地开发：make infra 起依赖（pg 5433 / redis 6380），代码用 uv / npm 直接跑
#   B. 容器部署：make up    起全套（web 8080 / api 8000），pg / redis 只在内部网络
# ============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

API_DIR   := apps/api
WEB_DIR   := apps/web
DC        ?= docker compose
INFRA_DC  ?= docker compose -f infra/docker-compose.yml

# ---------------------------------------------------------------- 帮助

.PHONY: help
help: ## 显示所有可用命令
	@awk 'BEGIN {FS = ":.*?## "; printf "\n\033[1m主理人 Agent\033[0m\n\n用法: make \033[36m<命令>\033[0m\n"} \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z_0-9-]+:.*?## / { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""

# ---------------------------------------------------------------- 准备

##@ 准备

.PHONY: env
env: ## 从 .env.example 生成 .env（已存在则跳过，不覆盖）
	@[ -f .env ] || { cp .env.example .env; echo "  已生成 .env（compose 用）"; }
	@[ -f $(API_DIR)/.env ] || { cp $(API_DIR)/.env.example $(API_DIR)/.env; echo "  已生成 $(API_DIR)/.env（本地开发用）"; }
	@echo "  ⚠️  请检查 EMBEDDING_DIM 是否与数据库一致：make doctor"

.PHONY: install
install: ## 安装后端与前端依赖（uv sync + npm ci）
	cd $(API_DIR) && uv sync
	cd $(WEB_DIR) && npm ci

.PHONY: doctor
doctor: ## 环境自检：配置 / DB / Redis / 迁移版本 / 向量维度 / 预置数据
	cd $(API_DIR) && uv run python scripts/doctor.py

# ---------------------------------------------------------------- 本地开发

##@ 本地开发（依赖走 Docker，代码本地跑）

.PHONY: infra
infra: ## 启动基础设施（pg 5433 / redis 6380 / minio 9000-9001）
	$(INFRA_DC) up -d postgres redis minio
	@echo "  postgres → localhost:5433   redis → localhost:6380   minio → localhost:9000"

.PHONY: infra-down
infra-down: ## 停止基础设施
	$(INFRA_DC) down

.PHONY: infra-logs
infra-logs: ## 基础设施日志
	$(INFRA_DC) logs -f

.PHONY: migrate
migrate: ## 执行数据库迁移（alembic upgrade head）
	cd $(API_DIR) && uv run alembic upgrade head

.PHONY: migration
migration: ## 生成迁移：make migration m="add xxx"
	@test -n "$(m)" || { echo "用法: make migration m='说明'"; exit 1; }
	cd $(API_DIR) && uv run alembic revision --autogenerate -m "$(m)"
	@echo "  ⚠️  自动生成的结果必须人工审阅：ENUM / 部分唯一索引 / pgvector 常被漏检（见 docs/05 §1.1）"

.PHONY: downgrade
downgrade: ## 回滚一个版本
	cd $(API_DIR) && uv run alembic downgrade -1

.PHONY: dev-api
dev-api: ## 本地起 API（热重载，:8000）
	cd $(API_DIR) && uv run uvicorn app.main:app --reload --port 8000

.PHONY: dev-worker
dev-worker: ## 本地起 arq worker（同步 / 打标 / 检查队列）
	cd $(API_DIR) && uv run arq app.workers.settings.WorkerSettings

.PHONY: dev-web
dev-web: ## 本地起前端（Vite，:5173，/api 反代到 :8000）
	cd $(WEB_DIR) && npm run dev

# ---------------------------------------------------------------- 测试与质量

##@ 测试与质量

.PHONY: test
test: test-api test-web ## 全量测试（后端 pytest + 前端类型检查）

.PHONY: test-api
test-api: ## 后端测试
	cd $(API_DIR) && uv run pytest tests/ -q -rs

.PHONY: test-unit
test-unit: ## 仅不依赖数据库的单测
	cd $(API_DIR) && uv run pytest tests/test_review_rules.py -q

.PHONY: test-integration
test-integration: ## 仅集成测试（需要 Postgres 已迁移）
	cd $(API_DIR) && uv run pytest tests/test_workspace_flow.py -q -rs

.PHONY: test-web
test-web: ## 前端类型检查 + 生产构建
	cd $(WEB_DIR) && npm run build

.PHONY: lint
lint: ## 后端 ruff 检查 + 迁移漂移检查
	cd $(API_DIR) && uv run ruff check app scripts
	cd $(API_DIR) && uv run alembic check || echo "  ↑ alembic check 有差异，见 TODO P0-2（pgvector 维度）"

.PHONY: lint-fix
lint-fix: ## 自动修复 ruff 可修项
	cd $(API_DIR) && uv run ruff check --fix app scripts tests

.PHONY: check
check: lint test ## 提交前全量门禁（lint + 测试）

# ---------------------------------------------------------------- Docker

##@ Docker 构建与部署

.PHONY: build
build: ## 构建 api / web 镜像
	$(DC) build

.PHONY: build-api
build-api: ## 仅构建 api 镜像（api / worker / migrate 共用）
	$(DC) build api

.PHONY: build-dev
build-dev: ## 构建含 dev 依赖的测试镜像（pytest / ruff）
	$(DC) -f docker-compose.yml build api
	docker build --target dev -t nda-api:dev $(API_DIR)

.PHONY: up
up: ## 构建并启动全套（web :8080，api :8000）
	$(DC) up -d --build
	@echo ""
	@echo "  Web      → http://localhost:$${WEB_PORT:-8080}"
	@echo "  API 文档 → http://localhost:$${API_PORT:-8000}/docs"
	@echo "  查看日志 → make logs"

.PHONY: down
down: ## 停止整套（保留数据卷）
	$(DC) down

.PHONY: down-clean
down-clean: ## 停止并删除数据卷（⚠️ 会清空数据库）
	$(DC) down -v

.PHONY: restart
restart: ## 重启 api / worker / web（不重建镜像）
	$(DC) restart api worker web

.PHONY: rebuild
rebuild: ## 重建并滚动更新（改了代码后用这个）
	$(DC) up -d --build --remove-orphans

.PHONY: logs
logs: ## 跟随全部服务日志
	$(DC) logs -f --tail=120

.PHONY: logs-api
logs-api: ## 跟随 api 日志
	$(DC) logs -f --tail=200 api

.PHONY: logs-worker
logs-worker: ## 跟随 worker 日志
	$(DC) logs -f --tail=200 worker

.PHONY: ps
ps: ## 查看服务状态与健康检查
	$(DC) ps

.PHONY: migrate-docker
migrate-docker: ## 在容器内执行迁移（一次性任务）
	$(DC) run --rm migrate

.PHONY: sh-api
sh-api: ## 进入 api 容器
	$(DC) exec api bash

.PHONY: sh-worker
sh-worker: ## 进入 worker 容器
	$(DC) exec worker bash

.PHONY: db-shell
db-shell: ## 进入数据库 psql
	$(DC) exec postgres psql -U nda -d nda

.PHONY: compose-config
compose-config: ## 校验 compose 文件并渲染最终配置
	$(DC) config --quiet && echo "  docker-compose.yml 校验通过"
	$(INFRA_DC) config --quiet && echo "  infra/docker-compose.yml 校验通过"

.PHONY: smoke
smoke: ## 部署后冒烟：探活 web 与 api
	@curl -fsS http://localhost:$${API_PORT:-8000}/health && echo ""
	@curl -fsS -o /dev/null -w "  web → HTTP %{http_code}\n" http://localhost:$${WEB_PORT:-8080}/
	@curl -fsS http://localhost:$${WEB_PORT:-8080}/api/v1/materials/stats | head -c 200 && echo ""

# ---------------------------------------------------------------- 清理

##@ 清理

.PHONY: clean
clean: ## 清理构建产物与缓存（保留依赖）
	rm -rf $(WEB_DIR)/dist
	find $(API_DIR) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(API_DIR)/.pytest_cache $(API_DIR)/.ruff_cache
	@echo "  已清理 dist / __pycache__ / 测试缓存"

.PHONY: clean-all
clean-all: clean ## 连依赖与虚拟环境一起清掉
	rm -rf $(WEB_DIR)/node_modules $(API_DIR)/.venv
	@echo "  已清理 node_modules / .venv（重新 make install）"

.PHONY: clean-docker
clean-docker: ## 删除本项目镜像与悬空层
	-docker rmi nda-api:latest nda-web:latest nda-api:dev 2>/dev/null || true
	-docker image prune -f
