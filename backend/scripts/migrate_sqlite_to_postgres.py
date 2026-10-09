"""
Copy all TruHire data from a SQLite database into PostgreSQL.

    python -m backend.scripts.migrate_sqlite_to_postgres \
        --source sqlite:///./truhire.db \
        --target "postgresql+psycopg://postgres:<password>@localhost:5432/truhire"

--target defaults to DATABASE_URL from .env. The schema is created from the SQLAlchemy
models, every table is copied in foreign-key order inside ONE transaction (all or
nothing), and row counts are verified afterwards. The SQLite file is only read, never
modified, so it stays as a backup. A non-empty target is refused unless --replace is given.
"""
import argparse
import sys

from sqlalchemy import create_engine, func, inspect, select

from backend.config import settings
from backend.database import Base
import backend.models  # noqa: F401  (registers every table on Base.metadata)

CHUNK = 500


def _strip_nul(value):
    """PostgreSQL text/JSON can't hold NUL (0x00) characters; SQLite can. Drop them."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {_strip_nul(k): _strip_nul(v) for k, v in value.items()}
    return value


def migrate(source_url: str, target_url: str, replace: bool = False) -> dict:
    if not source_url.startswith("sqlite"):
        raise SystemExit("--source must be a sqlite:/// URL")
    if not target_url.startswith("postgresql"):
        raise SystemExit("--target must be a postgresql+psycopg:// URL")

    source = create_engine(source_url)
    target = create_engine(target_url)
    tables = Base.metadata.sorted_tables  # parents before children

    source_tables = set(inspect(source).get_table_names())
    unknown = source_tables - {t.name for t in tables}
    if unknown:
        print(f"Note: SQLite tables not in the current models are skipped: {sorted(unknown)}")

    Base.metadata.create_all(target)

    with target.connect() as conn:
        populated = [t.name for t in tables if conn.execute(select(func.count()).select_from(t)).scalar()]
    if populated and not replace:
        raise SystemExit(f"Target already has data in {populated}; re-run with --replace to overwrite it.")

    counts = {}
    sanitized = []
    with source.connect() as src, target.begin() as dst:
        if populated:
            for table in reversed(tables):
                dst.execute(table.delete())
        for table in tables:
            if table.name not in source_tables:
                counts[table.name] = 0
                continue
            # Only columns that exist in the source; newer model columns fall back to defaults.
            source_cols = {c["name"] for c in inspect(source).get_columns(table.name)}
            cols = [c for c in table.columns if c.name in source_cols]
            copied = 0
            result = src.execute(select(*cols))
            while True:
                rows = result.fetchmany(CHUNK)
                if not rows:
                    break
                batch = [dict(zip([c.name for c in cols], row)) for row in rows]
                for record in batch:
                    for key, value in record.items():
                        clean = _strip_nul(value)
                        if clean != value:
                            sanitized.append(f"{table.name}.{key} (id={record.get('id') or record.get('name')})")
                            record[key] = clean
                dst.execute(table.insert(), batch)
                copied += len(rows)
            counts[table.name] = copied

    with source.connect() as src, target.connect() as dst:
        mismatches = []
        for table in tables:
            if table.name not in source_tables:
                continue
            a = src.execute(select(func.count()).select_from(table)).scalar()
            b = dst.execute(select(func.count()).select_from(table)).scalar()
            if a != b:
                mismatches.append(f"{table.name}: sqlite={a} postgres={b}")
    if mismatches:
        raise SystemExit("Row count verification FAILED: " + "; ".join(mismatches))
    for field in sanitized:
        print(f"Note: removed NUL characters from {field}")
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="sqlite:///./truhire.db")
    parser.add_argument("--target", default=settings.DATABASE_URL)
    parser.add_argument("--replace", action="store_true", help="overwrite a non-empty target database")
    args = parser.parse_args(argv)

    counts = migrate(args.source, args.target, replace=args.replace)
    width = max(len(n) for n in counts)
    for name, n in counts.items():
        print(f"  {name.ljust(width)}  {n}")
    print(f"Migrated {sum(counts.values())} rows across {len(counts)} tables; row counts verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
