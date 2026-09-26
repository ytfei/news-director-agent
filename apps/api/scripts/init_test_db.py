"""创建 / 重置独立测试库。

    uv run python scripts/init_test_db.py            # 建库 + 迁移
    uv run python scripts/init_test_db.py --reset    # 清空重建
    uv run python scripts/init_test_db.py --seed     # 附加少量演示数据（手动 UI 验收用）

为什么需要它：集成测试与开发共用同一个库时，测试数据会污染开发数据，
验收结果也不可复现（TODO D13）。CI 的前置条件同样是"有一套干净的库"。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.core.config import settings  # noqa: E402

OK, WARN, ERR = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"


def _plain_dsn(url: str) -> str:
    """SQLAlchemy 风格 URL → psycopg 可直接用的 DSN。"""
    return url.replace("+psycopg", "").replace("+asyncpg", "")


def _admin_url() -> str:
    """连到默认库（nda）去建库。"""
    return _plain_dsn(settings.DATABASE_URL_SYNC).rsplit("/", 1)[0] + "/nda"


def _test_db_name() -> str:
    return settings.TEST_DATABASE_URL_SYNC.rsplit("/", 1)[-1].split("?")[0]


def ensure_database() -> bool:
    import psycopg

    name = _test_db_name()
    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        exists = conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone()
        if exists:
            print(f"  {OK} 测试库已存在：{name}")
            return False
        # CREATE DATABASE 不能在事务里执行 → autocommit
        conn.execute(f'create database "{name}"')
        print(f"  {OK} 已创建测试库：{name}")
        return True


def reset_schema() -> None:
    import psycopg

    name = _test_db_name()
    with psycopg.connect(_admin_url(), autocommit=True) as conn:
        conn.execute(f'drop database if exists "{name}" with (force)')
        conn.execute(f'create database "{name}"')
    print(f"  {OK} 已重置测试库：{name}")


def run_migrations() -> int:
    env = {**os.environ, "DATABASE_URL_SYNC": settings.TEST_DATABASE_URL_SYNC}
    print(f"  · 迁移 → {_test_db_name()}")
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    tail = (result.stdout or result.stderr).strip().splitlines()[-3:]
    for line in tail:
        print("    ", line)
    return result.returncode


def seed() -> None:
    """少量演示数据：便于手动 UI 验收时页面不空。"""
    import asyncio

    async def _seed() -> None:
        from app.core.database import SessionLocal
        from sqlalchemy import text

        async with SessionLocal() as s:
            topics = await s.execute(
                text("select count(*) from topics where is_system")
            )
            prompts = await s.execute(
                text("select count(*) from prompt_templates where is_official")
            )
            print(f"  {OK} 预置数据：系统主题 {topics.scalar()} · 官方提示词 {prompts.scalar()}")
            print(f"  {WARN} 资讯数据请用「数据源」页手动触发同步（真机 tushare）")
            await s.commit()

    # seed 只依赖迁移里已有的预置数据，这里仅做核对
    asyncio.run(_seed())


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化独立测试库")
    parser.add_argument("--reset", action="store_true", help="先删除再重建")
    parser.add_argument("--seed", action="store_true", help="附加演示数据")
    args = parser.parse_args()

    print("\n\033[1m初始化测试库\033[0m\n")
    try:
        if args.reset:
            reset_schema()
        ensure_database()
    except Exception as exc:  # noqa: BLE001
        print(f"  {ERR} 无法连接 Postgres：{str(exc)[:200]}")
        print("     先启动基础设施：make infra")
        return 1

    code = run_migrations()
    if code != 0:
        return code

    if args.seed:
        seed()

    print(f"\n{OK} 完成。测试会写入 {_test_db_name()}，开发库不受影响\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
