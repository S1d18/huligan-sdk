"""
Huligan SDK — Web scraping with pagination and error handling.

Scrapes quotes from quotes.toscrape.com (a safe scraping sandbox).
Demonstrates:
  - Extracting structured data via locators (NOT page.evaluate)
  - Clicking through paginated pages
  - Graceful error handling (timeouts, missing elements)
  - Stopping after N pages or when no more pages exist
"""
import asyncio
from dataclasses import dataclass
from huligan import Browser


PROXY = "socks5://user:pass@ip:port"

# Target site — quotes.toscrape.com is a purpose-built scraping sandbox
START_URL = "https://quotes.toscrape.com/"

# Maximum number of pages to scrape (safety limit)
MAX_PAGES = 5

# Timeout for page loads (ms)
PAGE_TIMEOUT = 15000


@dataclass
class Quote:
    text: str
    author: str
    tags: list


async def scrape_page(page) -> list:
    """
    Extract all quotes from the current page using locators.

    Returns a list of Quote objects.
    """
    quotes = []

    # Each quote is in a div.quote container
    quote_elements = page.locator("div.quote")
    count = await quote_elements.count()

    for i in range(count):
        quote_el = quote_elements.nth(i)
        try:
            # Extract the quote text
            text_el = quote_el.locator("span.text")
            text = await text_el.text_content() if await text_el.count() > 0 else ""

            # Extract the author
            author_el = quote_el.locator("small.author")
            author = await author_el.text_content() if await author_el.count() > 0 else "Unknown"

            # Extract tags
            tag_elements = quote_el.locator("a.tag")
            tag_count = await tag_elements.count()
            tags = []
            for t in range(tag_count):
                tag_text = await tag_elements.nth(t).text_content()
                if tag_text:
                    tags.append(tag_text.strip())

            if text:
                quotes.append(Quote(
                    text=text.strip(),
                    author=author.strip(),
                    tags=tags,
                ))

        except Exception as e:
            print(f"    Warning: failed to extract quote {i}: {e}")
            continue

    return quotes


async def has_next_page(page) -> bool:
    """Check if a 'Next' button exists on the current page."""
    next_btn = page.locator("li.next a")
    return await next_btn.count() > 0


async def click_next_page(page):
    """Click the 'Next' button and wait for the new page to load."""
    next_btn = page.locator("li.next a")
    await next_btn.click()
    # Wait for the page content to reload
    await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT)
    # Wait for quotes to appear on the new page
    await page.locator("div.quote").first.wait_for(state="visible", timeout=PAGE_TIMEOUT)


async def main():
    print("Huligan — Scraping with pagination")
    print(f"Target: {START_URL}")
    print(f"Max pages: {MAX_PAGES}")
    print("=" * 55)

    all_quotes = []

    async with Browser(proxy=PROXY) as browser:
        page = await browser.new_page()

        # Navigate to the first page
        try:
            await page.goto(START_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        except Exception as e:
            print(f"Failed to load start page: {e}")
            return

        # Wait for quotes to be visible
        try:
            await page.locator("div.quote").first.wait_for(state="visible", timeout=PAGE_TIMEOUT)
        except Exception:
            print("No quotes found on the page. Site may be down.")
            return

        current_page = 1

        while current_page <= MAX_PAGES:
            print(f"\n--- Page {current_page} ({page.url}) ---")

            # Extract quotes from this page
            try:
                page_quotes = await scrape_page(page)
                all_quotes.extend(page_quotes)
                print(f"  Extracted {len(page_quotes)} quotes")

                # Show first quote as a preview
                if page_quotes:
                    q = page_quotes[0]
                    preview = q.text[:60] + "..." if len(q.text) > 60 else q.text
                    print(f"  First: {preview} — {q.author}")

            except Exception as e:
                print(f"  Error extracting quotes: {e}")
                # Continue to next page anyway
                pass

            # Check if there is a next page
            if current_page >= MAX_PAGES:
                print(f"\n  Reached max pages limit ({MAX_PAGES}).")
                break

            try:
                if not await has_next_page(page):
                    print("\n  No more pages (last page reached).")
                    break

                # Click next and wait for navigation
                await click_next_page(page)
                current_page += 1

            except Exception as e:
                print(f"\n  Failed to navigate to next page: {e}")
                break

    # Print collected data
    print("\n" + "=" * 55)
    print(f"SCRAPING COMPLETE: {len(all_quotes)} quotes from {current_page} pages")
    print("=" * 55)

    for i, q in enumerate(all_quotes, 1):
        tags_str = ", ".join(q.tags) if q.tags else "none"
        print(f"\n  [{i}] {q.text}")
        print(f"      — {q.author}")
        print(f"      Tags: {tags_str}")

    # Summary stats
    authors = set(q.author for q in all_quotes)
    all_tags = set(tag for q in all_quotes for tag in q.tags)
    print(f"\n  Unique authors: {len(authors)}")
    print(f"  Unique tags: {len(all_tags)}")


if __name__ == "__main__":
    asyncio.run(main())
