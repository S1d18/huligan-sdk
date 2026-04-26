"""
Huligan SDK — Parallel browser instances with asyncio.

Launches multiple antidetect browsers concurrently using asyncio.Semaphore
to limit how many run at the same time (to avoid overwhelming system resources).

Each browser gets its own proxy and fingerprint. Results are printed as they
complete — no waiting for all tasks to finish before seeing output.
"""
import asyncio
from huligan import Browser


# Maximum number of browsers running at the same time
MAX_CONCURRENT = 3

# Each task has its own proxy and target URL
TASKS = [
    {"proxy": "socks5://user1:pass1@proxy1.example.com:1080", "url": "https://httpbin.org/ip"},
    {"proxy": "socks5://user2:pass2@proxy2.example.com:1080", "url": "https://httpbin.org/headers"},
    {"proxy": "socks5://user3:pass3@proxy3.example.com:1080", "url": "https://httpbin.org/user-agent"},
    {"proxy": "socks5://user4:pass4@proxy4.example.com:1080", "url": "https://httpbin.org/ip"},
    {"proxy": "socks5://user5:pass5@proxy5.example.com:1080", "url": "https://httpbin.org/headers"},
    {"proxy": "socks5://user6:pass6@proxy6.example.com:1080", "url": "https://httpbin.org/user-agent"},
]


async def run_task(task_id: int, proxy: str, url: str, semaphore: asyncio.Semaphore) -> dict:
    """
    Run a single browser task within the semaphore limit.

    Opens the URL, extracts the page title and first text content,
    then closes the browser. Handles errors gracefully.
    """
    result = {
        "task_id": task_id,
        "proxy": proxy,
        "url": url,
        "title": None,
        "content_preview": None,
        "error": None,
    }

    # Semaphore ensures at most MAX_CONCURRENT browsers run simultaneously
    async with semaphore:
        print(f"[Task {task_id}] Starting (proxy: {proxy.split('@')[-1]})")
        browser = None
        try:
            browser = Browser(proxy=proxy)
            await browser.start()

            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # Extract page title
            result["title"] = await page.title()

            # Extract a preview of the page content using locators
            pre = page.locator("pre")
            if await pre.count() > 0:
                text = await pre.first.text_content()
                # Trim to first 80 chars for the preview
                result["content_preview"] = text.strip()[:80] if text else None

            print(f"[Task {task_id}] Done: {result['title']}")

        except Exception as e:
            result["error"] = str(e)
            print(f"[Task {task_id}] Failed: {e}")

        finally:
            # Always clean up the browser, even on errors
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass

    return result


async def main():
    print("Huligan — Parallel browser execution")
    print(f"Tasks: {len(TASKS)}, Max concurrent: {MAX_CONCURRENT}")
    print("=" * 55)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    # Launch all tasks concurrently — semaphore controls parallelism
    tasks = [
        run_task(i + 1, t["proxy"], t["url"], semaphore)
        for i, t in enumerate(TASKS)
    ]
    results = await asyncio.gather(*tasks)

    # Print summary
    print("\n" + "=" * 55)
    print("RESULTS SUMMARY")
    print("=" * 55)

    for r in results:
        status = "OK" if r["error"] is None else f"FAIL: {r['error'][:50]}"
        print(f"  Task {r['task_id']}: {status}")
        if r["title"]:
            print(f"    Title: {r['title']}")
        if r["content_preview"]:
            print(f"    Content: {r['content_preview'][:60]}...")

    ok = sum(1 for r in results if r["error"] is None)
    print(f"\nCompleted: {ok}/{len(results)} tasks succeeded")


if __name__ == "__main__":
    asyncio.run(main())
