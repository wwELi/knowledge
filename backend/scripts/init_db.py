"""Initialize the kb database by running `alembic upgrade head` (idempotent).

Usage: cd backend && uv run python scripts/init_db.py
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


def main() -> int:
    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    try:
        command.upgrade(alembic_cfg, "head")
    except OperationalError as exc:
        print(f"连接数据库失败: {exc}", file=sys.stderr)
        return 1
    print("OK: database is at alembic head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
