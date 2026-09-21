"""Bootstrap a fresh Postgres DB (the alembic chain isn't rooted) and stamp it at head.
Usage: python scripts/init_db.py. Reads DATABASE_URL the same way core.config does."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import Enum as SAEnum, text
from sqlalchemy.ext.asyncio import create_async_engine

SCHEMAS = ["accounts", "catalog", "commerce", "admin", "system"]


async def main() -> None:
    from core.config import settings
    import models
    from core.db import Base

    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)

    async with engine.begin() as conn:
        for schema in SCHEMAS:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))

        await conn.execute(text(f"SET search_path TO {', '.join(SCHEMAS)}, public"))

        # Postgres ENUM types must exist before any table that references them.
        enum_types = {}
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if isinstance(column.type, SAEnum):
                    enum_types[column.type.name] = column.type
        for enum_type in enum_types.values():
            await conn.run_sync(lambda sync_conn, et=enum_type: et.create(sync_conn, checkfirst=True))

        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database schema created.")

    # Mark the DB as being at the current alembic head, so `alembic upgrade head`
    # applies cleanly on top of this bootstrap instead of trying to replay history.
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI_SYNC)
    command.stamp(alembic_cfg, "head")
    print("Stamped database at alembic head.")


if __name__ == "__main__":
    asyncio.run(main())
