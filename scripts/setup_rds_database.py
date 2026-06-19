"""Create the configured PostgreSQL database if it does not exist.

This script reads DATABASE_URL from .env, connects to the maintenance
database named "postgres", and creates the target database from the URL.
It intentionally avoids printing credentials.
"""

from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2
from psycopg2 import sql


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    env = load_env(Path(".env"))
    database_url = env["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlparse(database_url)
    target_db = parsed.path.lstrip("/")
    if not target_db:
        raise SystemExit("DATABASE_URL must include a database name")

    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname="postgres",
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        connect_timeout=15,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if cur.fetchone():
                print(f"database_exists:{target_db}")
                return
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
            print(f"database_created:{target_db}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
