"""
run_local.py — Run the full ETL pipeline locally (no Docker / Airflow needed).

Executes: scrape → transform → load sequentially.
"""

import sys
import os
import time

# Add scripts/ to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

# Local paths (instead of /tmp and /opt/airflow/data used in Docker)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_JSON = os.path.join(PROJECT_DIR, "data", "books_raw.json")
CLEAN_CSV = os.path.join(PROJECT_DIR, "data", "books_clean.csv")
DB_PATH = os.path.join(PROJECT_DIR, "data", "books.db")


def main():
    start = time.time()

    # ── Step 1: Scrape ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 1/3 — SCRAPING (Playwright async)")
    print("=" * 60)
    from scraper import scrape_and_save
    scrape_and_save(output_path=RAW_JSON)

    # ── Step 2: Transform ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 2/3 — TRANSFORMING (Pandas)")
    print("=" * 60)
    from transform import transform
    transform(input_path=RAW_JSON, output_path=CLEAN_CSV)

    # ── Step 3: Load ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  STEP 3/3 — LOADING (SQLite)")
    print("=" * 60)
    from load import load
    load(csv_path=CLEAN_CSV, db_path=DB_PATH)

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"  [OK] PIPELINE COMPLETE -- {elapsed:.1f}s total")
    print(f"  -> Raw JSON:  {RAW_JSON}")
    print(f"  -> Clean CSV: {CLEAN_CSV}")
    print(f"  -> SQLite DB: {DB_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
