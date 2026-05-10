""" Harsh Gupta - Objective is to make a Graph so everything works in order 
books_pipeline.py — Airflow DAG for the Books ETL pipeline.

Three sequential tasks:
  1. scrape_books  → Run Playwright async scraper, write /tmp/books_raw.json
  2. transform_books → Read JSON, clean with Pandas, write /tmp/books_clean.csv
  3. load_books    → Read CSV, upsert into SQLite at /opt/airflow/data/books.db

Schedule: @daily | Retries: 1 (5 min delay) | Catchup: False
"""

import sys
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# ---------------------------------------------------------------------------
# Ensure the /opt/airflow/scripts directory is on the Python path so we can
# import our modules without installing them as packages.
# ---------------------------------------------------------------------------
SCRIPTS_DIR = "/opt/airflow/scripts"
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ---------------------------------------------------------------------------
# File paths (shared between tasks via the filesystem)
# ---------------------------------------------------------------------------
RAW_JSON = "/tmp/books_raw.json"
CLEAN_CSV = "/tmp/books_clean.csv"
DB_PATH = "/opt/airflow/data/books.db"


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------
def _scrape_books(**kwargs):
    """Run the Playwright async scraper and persist raw JSON."""
    from scraper import scrape_and_save
    scrape_and_save(output_path=RAW_JSON)


def _transform_books(**kwargs):
    """Read raw JSON, clean it, and write a CSV."""
    from transform import transform
    transform(input_path=RAW_JSON, output_path=CLEAN_CSV)


def _load_books(**kwargs):
    """Read cleaned CSV and upsert rows into SQLite."""
    from load import load
    load(csv_path=CLEAN_CSV, db_path=DB_PATH)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
}

with DAG(
    dag_id="books_etl_pipeline",
    default_args=default_args,
    description="Scrape books.toscrape.com → clean with Pandas → load into SQLite",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["etl", "books", "scraping"],
) as dag:

    scrape = PythonOperator(
        task_id="scrape_books",
        python_callable=_scrape_books,
    )

    transform = PythonOperator(
        task_id="transform_books",
        python_callable=_transform_books,
    )

    load = PythonOperator(
        task_id="load_books",
        python_callable=_load_books,
    )

    # Linear dependency chain
    scrape >> transform >> load
