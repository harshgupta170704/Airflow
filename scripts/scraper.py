"""
scraper.py — Async Playwright scraper for books.toscrape.com

Scrapes all 50 pages of book listings, then visits each book's detail page
to extract the product description. Uses a semaphore to limit concurrent
detail-page fetches and adds a small sleep between visits for rate limiting.
"""

import asyncio
import json
import logging
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("scraper")

# ---------------------------------------------------------------------------
# Constants / tunables
# ---------------------------------------------------------------------------
BASE_URL = "https://books.toscrape.com"
CATALOGUE_URL = f"{BASE_URL}/catalogue/page-{{}}.html"  # page number placeholder
CONCURRENCY_LIMIT = 5          # max parallel detail-page fetches
RATE_LIMIT_SLEEP = 0.7         # seconds to sleep between page visits
PAGE_TIMEOUT_MS = 30_000       # 30 s timeout for navigation
DETAIL_TIMEOUT_MS = 20_000     # 20 s timeout for detail pages

# Star-rating CSS class → word mapping (used during extraction)
RATING_CLASSES = {
    "One": "One",
    "Two": "Two",
    "Three": "Three",
    "Four": "Four",
    "Five": "Five",
}


# ---------------------------------------------------------------------------
# Helper: extract books from a single catalogue page
# ---------------------------------------------------------------------------
async def _extract_books_from_listing(page: Page) -> List[Dict]:
    """
    Parse the current listing page and return a list of partial book dicts.
    Each dict has: title, price, rating, availability, category, detail_url.
    """
    books: List[Dict] = []

    # Every book is inside an <article class="product_pod">
    articles = await page.query_selector_all("article.product_pod")

    for article in articles:
        try:
            # --- title & detail URL ---
            link_el = await article.query_selector("h3 a")
            title = await link_el.get_attribute("title") if link_el else ""
            relative_url = await link_el.get_attribute("href") if link_el else ""
            # Build absolute URL (links are relative to /catalogue/)
            detail_url = (
                f"{BASE_URL}/catalogue/{relative_url.lstrip('../')}"
                if relative_url
                else ""
            )

            # --- price ---
            price_el = await article.query_selector(".price_color")
            price = (await price_el.inner_text()).strip() if price_el else ""

            # --- star rating ---
            star_el = await article.query_selector("p.star-rating")
            rating = ""
            if star_el:
                classes = await star_el.get_attribute("class")  # e.g. "star-rating Three"
                for word in (classes or "").split():
                    if word in RATING_CLASSES:
                        rating = word
                        break

            # --- availability ---
            avail_el = await article.query_selector(".availability")
            availability = (await avail_el.inner_text()).strip() if avail_el else ""

            books.append(
                {
                    "title": title,
                    "price": price,
                    "rating": rating,
                    "availability": availability,
                    "category": "",       # filled from breadcrumb on detail page
                    "description": "",    # filled from detail page
                    "detail_url": detail_url,
                }
            )
        except Exception as exc:
            logger.warning("Failed to parse an article on listing page: %s", exc)

    return books


# ---------------------------------------------------------------------------
# Helper: check if there is a "next" button on the listing page
# ---------------------------------------------------------------------------
async def _has_next_page(page: Page) -> bool:
    next_btn = await page.query_selector("li.next a")
    return next_btn is not None


# ---------------------------------------------------------------------------
# Scrape all listing pages (paginate until no "next" button)
# ---------------------------------------------------------------------------
async def scrape_all_listings(context: BrowserContext) -> List[Dict]:
    """
    Iterate over all catalogue pages (1 → N) and collect partial book dicts.
    """
    all_books: List[Dict] = []
    page = await context.new_page()

    page_num = 1
    while True:
        url = CATALOGUE_URL.format(page_num)
        logger.info("Scraping listing page %d — %s", page_num, url)

        try:
            await page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception as exc:
            logger.error("Failed to load listing page %d: %s", page_num, exc)
            break

        books = await _extract_books_from_listing(page)
        all_books.extend(books)
        logger.info("  ↳ extracted %d books (total so far: %d)", len(books), len(all_books))

        if not await _has_next_page(page):
            logger.info("No 'next' button on page %d — done with listings.", page_num)
            break

        page_num += 1
        await asyncio.sleep(RATE_LIMIT_SLEEP)

    await page.close()
    return all_books


# ---------------------------------------------------------------------------
# Fetch description + category from a single detail page
# ---------------------------------------------------------------------------
async def _fetch_detail(
    context: BrowserContext,
    book: Dict,
    semaphore: asyncio.Semaphore,
) -> None:
    """
    Visit a book's detail page and populate `description` and `category`.
    On failure, log the error and leave description empty.
    """
    async with semaphore:
        page: Optional[Page] = None
        try:
            page = await context.new_page()
            await page.goto(
                book["detail_url"],
                timeout=DETAIL_TIMEOUT_MS,
                wait_until="domcontentloaded",
            )

            # --- product description ---
            desc_el = await page.query_selector("#product_description ~ p")
            if desc_el:
                book["description"] = (await desc_el.inner_text()).strip()
            else:
                book["description"] = ""

            # --- category from breadcrumb ---
            # Breadcrumb: Home > Books > <Category> > <Title>
            breadcrumbs = await page.query_selector_all("ul.breadcrumb li a")
            if len(breadcrumbs) >= 3:
                book["category"] = (await breadcrumbs[2].inner_text()).strip()
            else:
                book["category"] = ""

            logger.info("  ✓ detail fetched: %s", book["title"][:50])

        except Exception as exc:
            logger.warning(
                "  ✗ detail failed for '%s' (%s): %s",
                book["title"][:40],
                book["detail_url"],
                exc,
            )
            book["description"] = ""

        finally:
            if page:
                await page.close()
            await asyncio.sleep(RATE_LIMIT_SLEEP)


# ---------------------------------------------------------------------------
# Orchestrate detail fetching with concurrency control
# ---------------------------------------------------------------------------
async def enrich_with_details(
    context: BrowserContext,
    books: List[Dict],
) -> None:
    """
    Visit every book's detail page concurrently (bounded by CONCURRENCY_LIMIT)
    and fill in description + category.
    """
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    logger.info(
        "Fetching details for %d books (concurrency=%d) …",
        len(books),
        CONCURRENCY_LIMIT,
    )
    tasks = [_fetch_detail(context, book, semaphore) for book in books]
    await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Public entry point — run the full scrape
# ---------------------------------------------------------------------------
async def run_scraper() -> List[Dict]:
    """
    Launch a headless Chromium browser, scrape all listings, enrich each book
    with its description and category from the detail page, and return the
    complete list of book dicts.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
        )

        try:
            # Step 1: scrape all catalogue listing pages
            books = await scrape_all_listings(context)
            # Step 2: visit each detail page to get description + category
            await enrich_with_details(context, books)
        finally:
            await context.close()
            await browser.close()

    logger.info("Scraping complete — %d books collected.", len(books))
    return books


# ---------------------------------------------------------------------------
# CLI convenience: run scraper and dump JSON
# ---------------------------------------------------------------------------
def scrape_and_save(output_path: str = "/tmp/books_raw.json") -> str:
    """
    Synchronous wrapper that runs the async scraper and writes JSON output.
    Returns the output path.
    """
    books = asyncio.run(run_scraper())
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(books, fh, ensure_ascii=False, indent=2)
    logger.info("Raw data saved to %s (%d books)", output_path, len(books))
    return output_path


if __name__ == "__main__":
    scrape_and_save()
