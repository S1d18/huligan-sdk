"""Pattern 1 - connect an external Playwright-based automation framework to a
fully-wired Huligan browser over CDP.

Huligan launches the patched binary with the fingerprint .conf, proxy forwarder,
GeoIP timezone/language, WebRTC spoof, and JA4 pins already applied. Any tool that
can "connect over CDP" (a browser-agent / LLM-driven framework, a bare Playwright
client, ...) attaches to the running browser by URL - no adapter class required.

    pip install huligan[playwright]
    python cdp_connect_external_framework.py
"""
from huligan import FingerprintGenerator, launch_persistent


def main():
    # 1) Generate a fingerprint and write its .conf.
    profile = FingerprintGenerator().generate()
    conf_path = "identity.conf"
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(profile.to_conf())

    # 2) Launch the fully-wired antidetect browser. Add proxy="socks5://user:pass@ip:port"
    #    here to get the proxy forwarder + GeoIP + WebRTC spoofing wired automatically.
    session = launch_persistent(profile_path=conf_path, wait_for_cdp=True)
    try:
        print("Connect your framework over CDP at:", session.cdp_url)

        # 3) Hand session.cdp_url to ANY external Playwright-based framework via its
        #    connect-over-CDP entry point. Shown here with bare Playwright; substitute
        #    your framework's equivalent one-liner.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(session.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://abrahamjuliot.github.io/creepjs/", wait_until="domcontentloaded")
            print("Connected + navigated. Read detector output via LOCATORS, e.g.:")
            print("    page.locator('SELECTOR').text_content()")
            # page.evaluate() is blocked by patch 05_cdp_stealth; use locators instead.
            browser.close()
    finally:
        session.stop()

    # NOTE: fingerprint verdicts should be read from the headed window by an operator;
    # the CDP scraper can report a stale 100%.


if __name__ == "__main__":
    main()
