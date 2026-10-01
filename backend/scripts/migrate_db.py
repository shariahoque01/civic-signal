"""Add any model columns missing from an existing SQLite DB (create_all never alters tables).

    .venv/bin/python -m scripts.migrate_db
"""
from sqlalchemy import inspect, text

from app.database import Base, engine, init_db


def migrate() -> list[str]:
    init_db()  # creates missing tables
    added = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = col.type.compile(engine.dialect)
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                clause = f" DEFAULT {int(default) if isinstance(default, bool) else repr(default)}" if default is not None else ""
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ddl}{clause}'))
                added.append(f"{table.name}.{col.name}")
    return added


if __name__ == "__main__":
    print("added:", migrate() or "nothing")
