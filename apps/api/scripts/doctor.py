"""部署前自检：配置 → 连接 → 迁移版本 → 向量维度一致性。

    make doctor          # 或 cd apps/api && uv run python scripts/doctor.py

为什么需要它：
配置与库结构一旦不一致，症状往往出现在很远的地方（写入报错、检索退化成全表扫描、
`alembic check` 反复报差异）。这里把最容易踩的几处集中前置检测。

退出码：0 = 全部通过（允许 WARN）；1 = 存在 ERROR。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from app.core.config import settings  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

OK, WARN, ERR = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"

# 这些键的值在输出里一律打码（自检结果会进 CI 日志 / 工单）
SENSITIVE_PARTS = ("TOKEN", "PASSWORD", "SECRET", "KEY", "DATABASE_URL", "REDIS_URL", "DSN")

problems: list[str] = []


def is_sensitive(key: str) -> bool:
    upper = key.upper()
    return any(p in upper for p in SENSITIVE_PARTS)


def line(mark: str, title: str, detail: str = "") -> None:
    print(f"  {mark} {title}" + (f"  \033[2m{detail}\033[0m" if detail else ""))


def mask(url: str) -> str:
    """打印连接串时抹掉密码。"""
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    if "//" in head:
        scheme, creds = head.split("//", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}//{user}:***@{tail}"
    return f"***@{tail}"


print("\n\033[1m主理人 Agent · 环境自检\033[0m\n")

# ---------------------------------------------------------------- 1. 配置
print("配置")
line(OK, f"APP_ENV={settings.APP_ENV}", f"log={settings.LOG_LEVEL}")
line(OK, f"DATABASE_URL={mask(settings.DATABASE_URL)}")
line(OK, f"REDIS_URL={settings.REDIS_URL}")
if settings.TUSHARE_TOKEN:
    line(OK, "TUSHARE_TOKEN 已配置")
else:
    line(WARN, "TUSHARE_TOKEN 未配置", "同步任务会失败，可用 make infra 后才需要真机数据")

# 探测「环境变量覆盖 .env」：pydantic-settings 里 env var 优先级高于 .env 文件，
# 一旦被覆盖，同一份代码在不同机器上会读到不同的值，排查成本极高。
env_file = API_ROOT / ".env"
if env_file.exists():
    shadows: list[str] = []
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key, val = key.strip(), val.strip()
        actual = os.environ.get(key)
        if actual is not None and actual != val:
            # ★ 自检输出会进 CI 日志，敏感值一律打码
            masked = is_sensitive(key)
            shadows.append(
                f"{key}: .env={'***' if masked else (val or '(空)')} "
                f"→ 实际={'***' if masked else actual}"
            )
    if shadows:
        line(WARN, "环境变量覆盖了 .env", "；".join(shadows))
    else:
        line(OK, ".env 与实际生效值一致")

# ---------------------------------------------------------------- 2. 数据库
print("\n数据库")
try:
    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    with engine.connect() as conn:
        version = conn.execute(text("select version()")).scalar_one()
        line(OK, "连接成功", str(version).split(" ")[1] if version else "")

        # 2.1 迁移版本
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        head = script.get_current_head()
        current = MigrationContext.configure(conn).get_current_revision()
        if current == head:
            line(OK, f"迁移版本 = head（{current}）")
        else:
            line(ERR, f"迁移版本落后：current={current} head={head}", "执行 make migrate")
            problems.append("数据库迁移未到 head")

        # 2.2 向量维度一致性 ★ 最常见的部署事故
        dim = conn.execute(
            text(
                "select format_type(atttypid, atttypmod) from pg_attribute "
                "where attrelid = 'news_items'::regclass and attname = 'embedding'"
            )
        ).scalar()
        col_dim = int(str(dim).split("(")[1].rstrip(")")) if dim and "(" in str(dim) else None
        if col_dim is None:
            line(WARN, "news_items.embedding 不存在", "M1 迁移可能未执行")
        elif col_dim == settings.EMBEDDING_DIM:
            line(OK, f"向量维度一致：vector({col_dim})")
        else:
            line(
                ERR,
                f"向量维度不一致：库中 vector({col_dim}) vs 配置 EMBEDDING_DIM={settings.EMBEDDING_DIM}",
                "写入 embedding 会直接报错（TODO P0-2）",
            )
            problems.append("EMBEDDING_DIM 与库中向量列不一致")

        # 2.3 向量索引（>2000 维无法建 HNSW，检索会退化成全表扫描）
        has_idx = conn.execute(
            text(
                "select count(*) from pg_indexes where tablename = 'news_items' "
                "and indexname = 'ix_news_items_embedding'"
            )
        ).scalar_one()
        if has_idx:
            line(OK, "向量索引 ix_news_items_embedding 存在")
        else:
            line(WARN, "向量索引缺失", "语义检索走全表扫描；>2000 维时无解，见 TODO P0-2")

        # 2.4 关键表
        expected = [
            "news_items",
            "materials",
            "material_topics",
            "annotations",
            "review_reports",
            "review_findings",
            "fact_cards",
            "projects",
            "prompt_templates",
        ]
        rows = conn.execute(
            text("select tablename from pg_tables where schemaname = 'public'")
        ).scalars().all()
        present = set(rows)
        missing = [t for t in expected if t not in present]
        if missing:
            line(ERR, f"缺少表：{', '.join(missing)}")
            problems.append("缺少必要的表")
        else:
            line(OK, f"关键表齐全（public 共 {len(present)} 张）")

        # 2.5 预置数据
        topics = conn.execute(
            text("select count(*) from topics where user_id is null and is_system")
        ).scalar_one()
        prompts = conn.execute(
            text("select count(*) from prompt_templates where is_official")
        ).scalar_one()
        line(OK, f"预置数据：系统主题 {topics} 个 · 官方提示词 {prompts} 套")
    engine.dispose()
except Exception as exc:  # noqa: BLE001
    line(ERR, "数据库不可用", str(exc)[:160])
    problems.append("数据库不可用")

# ---------------------------------------------------------------- 3. Redis
print("\nRedis")
try:
    import redis as redis_sync

    client = redis_sync.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3)
    client.ping()
    line(OK, "连接成功", f"PING → {client.ping()}")
    client.close()
except Exception as exc:  # noqa: BLE001
    line(WARN, "Redis 不可用", f"{str(exc)[:120]}（worker / 缓存会退化为不可用）")

# ---------------------------------------------------------------- 3.5 模型
print("\n模型")
_key = settings.OPENAI_API_KEY
if _key:
    shown = f"{_key[:8]}***{_key[-4:]}" if len(_key) > 16 else "***"
    line(OK, "OPENAI_API_KEY 已配置", shown)
else:
    line(WARN, "未配置 OPENAI_API_KEY", "向量化与 LLM 降级为规则版；填 apps/api/.env")
line(
    OK,
    f"LLM_MODEL={settings.LLM_MODEL}",
    "推理模型：token 多为 reasoning，成本与延迟高" if settings.LLM_IS_REASONING else "",
)
line(OK, f"EMBEDDING_MODEL={settings.EMBEDDING_MODEL}", f"dim={settings.EMBEDDING_DIM}")
if settings.EMBEDDING_DIM > 2000:
    line(
        WARN,
        f"{settings.EMBEDDING_DIM} 维 > pgvector 索引上限 2000",
        "向量索引不会创建，语义检索退化为全表扫描；需索引时设 EMBEDDING_TRUNCATE_TO<=2000",
    )
line(OK, "真机连通性", "make models（doctor 不做真实调用，避免产生费用）")

# ---------------------------------------------------------------- 结论
print()
if problems:
    print("\033[31m自检未通过\033[0m：")
    for p in problems:
        print(f"  · {p}")
    sys.exit(1)
print("\033[32m自检通过\033[0m")
