"""
transform.py — Pandas-based data cleaning for scraped book data.

Reads raw JSON from the scraper, applies transformations (price parsing,
rating mapping, deduplication), and writes a clean CSV.
"""

import logging
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("transform")

# ---------------------------------------------------------------------------
# Rating word → integer mapping
# ---------------------------------------------------------------------------
RATING_MAP = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}


def transform(
    input_path: str = "/tmp/books_raw.json",
    output_path: str = "/tmp/books_clean.csv",
) -> str:
    """
    Read raw scraped JSON, clean it, and write a CSV.

    Cleaning steps:
      1. Convert price string ("£12.34") → float (12.34).
      2. Map rating words → integers (One→1 … Five→5).
      3. Strip whitespace from description & availability.
      4. Drop duplicate rows based on detail_url (keep first).

    Returns the output CSV path.
    """
    logger.info("Reading raw data from %s …", input_path)
    df = pd.read_json(input_path)
    logger.info("Loaded %d rows.", len(df))

    # ── 1. Price: remove currency symbol and convert to float ──────────────
    df["price"] = (
        df["price"]
        .astype(str)
        .str.replace("£", "", regex=False)
        .str.replace("Â", "", regex=False)   # handle encoding artefacts
        .str.strip()
        .apply(pd.to_numeric, errors="coerce")
    )
    logger.info("Price column converted to float.")

    # ── 2. Rating: word → integer ─────────────────────────────────────────
    df["rating"] = df["rating"].map(RATING_MAP).fillna(0).astype(int)
    logger.info("Rating column mapped to integers.")

    # ── 3. Strip whitespace from text columns ─────────────────────────────
    for col in ("description", "availability"):
        df[col] = df[col].astype(str).str.strip()
    logger.info("Whitespace stripped from description & availability.")

    # ── 4. Deduplicate on detail_url ──────────────────────────────────────
    before = len(df)
    df.drop_duplicates(subset="detail_url", keep="first", inplace=True)
    after = len(df)
    if before != after:
        logger.info("Dropped %d duplicate rows.", before - after)

    # ── Write output ──────────────────────────────────────────────────────
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Clean data written to %s (%d rows).", output_path, len(df))
    return output_path


if __name__ == "__main__":
    transform()
