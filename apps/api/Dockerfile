# syntax=docker/dockerfile:1.7
#
# 主理人 Agent · API / Worker 镜像
#
# 同一个镜像跑三种角色，避免"API 和 Worker 依赖漂移"这种经典事故：
#   - api      uvicorn app.main:app
#   - worker   arq app.workers.settings.WorkerSettings
#   - migrate  alembic upgrade head（一次性任务）
#
# 依赖装进 /app/.venv，两个阶段用同一个 python 基础镜像，所以 venv 可以直接拷过去。

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.11.0

# ---------------------------------------------------------------- builder
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ARG UV_VERSION
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

# 依赖层单独缓存：只要 pyproject / uv.lock 不变，改代码不会重装依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# curl 仅用于 HEALTHCHECK；tini 让 PID 1 能正确转发信号（否则 Ctrl-C / SIGTERM 杀不掉 uvicorn）
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app app      ./app
COPY --chown=app:app alembic  ./alembic
COPY --chown=app:app scripts  ./scripts
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app pyproject.toml ./
# scripts/ 故意保留：运维可以在真实环境里跑自检
#   docker compose exec api python scripts/doctor.py
# tests/ 不入生产镜像（只有 dev 阶段 COPY 全量）

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------- dev
# 含 dev 依赖（pytest / ruff / httpx），供 CI 与本地容器化测试使用：
#   docker build --target dev -t nda-api:dev apps/api
#   docker run --rm --network nda_default nda-api:dev
FROM python:${PYTHON_VERSION}-slim-bookworm AS dev

ARG UV_VERSION
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

CMD ["pytest", "tests/", "-q"]
