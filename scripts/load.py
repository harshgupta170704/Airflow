"""
load.py — Idempotent SQLite loader for cleaned book data.

Reads the clean CSV produced by the transform step, creates (or reuses)
a SQLite database, and upserts every row using INSERT … ON CONFLICT …
DO UPDATE SET, keyed on detail_url.
"""

import logging
import os
import sqlite3
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("loader")

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
DEFAULT_CSV = "/tmp/books_clean.csv"
DEFAULT_DB = "/opt/airflow/data/books.db"

# ---------------------------------------------------------------------------
# DDL: create the books table if it doesn't exist
# ---------------------------------------------------------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS books (
    detail_url   TEXT PRIMARY KEY,
    title        TEXT,
    price        REAL,
    rating       INTEGER,
    availability TEXT,
    category     TEXT,
    description  TEXT,
    scraped_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Upsert statement (idempotent — updates all non-key columns on conflict)
# ---------------------------------------------------------------------------
UPSERT_SQL = """
INSERT INTO books (detail_url, title, price, rating, availability, category, description)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(detail_url) DO UPDATE SET
    title        = excluded.title,
    price        = excluded.price,
    rating       = excluded.rating,
    availability = excluded.availability,
    category     = excluded.category,
    description  = excluded.description,
    scraped_at   = CURRENT_TIMESTAMP;
"""


def load(
    csv_path: str = DEFAULT_CSV,
    db_path: str = DEFAULT_DB,
) -> str:
    """
    Read the cleaned CSV and upsert every row into the SQLite `books` table.

    - Creates the database directory if it doesn't exist.
    - Creates the table on first run.
    - Uses INSERT … ON CONFLICT to make re-runs safe (idempotent).

    Returns the database file path.
    """
    # Ensure the directory for the DB file exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    logger.info("Reading cleaned CSV from %s …", csv_path)
    df = pd.read_csv(csv_path)
    logger.info("Loaded %d rows from CSV.", len(df))

    # Fill NaN descriptions with empty strings to avoid SQL errors
    df["description"] = df["description"].fillna("")

    # Connect to SQLite and create table
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    logger.info("Database ready at %s.", db_path)

    # Upsert rows
    rows = df[
        ["detail_url", "title", "price", "rating", "availability", "category", "description"]
    ].values.tolist()

    cursor.executemany(UPSERT_SQL, rows)
    conn.commit()
    logger.info("Upserted %d rows into 'books' table.", len(rows))

    # Quick verification
    count = cursor.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    logger.info("Total rows in 'books' table: %d", count)

    conn.close()
    return db_path


if __name__ == "__main__":
    load()
