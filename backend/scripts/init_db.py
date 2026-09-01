"""Apply backend/db/init.sql to the kb database (idempotent).

Usage: cd backend && uv run python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import config  # noqa: E402

SQL_PATH = BACKEND_ROOT / "db" / "init.sql"


async def main() -> int:
    sql = SQL_PATH.read_text(encoding="utf-8")
    try:
        async with await psycopg.AsyncConnection.connect(
            config.DATABASE_URL, autocommit=True
        ) as conn:
            await conn.execute(sql)
    except psycopg.OperationalError as exc:
        print(f"连接数据库失败: {exc}", file=sys.stderr)
        return 1
    print(f"OK: schema applied from {SQL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
