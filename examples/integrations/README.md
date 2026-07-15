# Integrating Huligan with external automation stacks

Huligan needs **no framework-specific adapter classes**. The antidetect payload is just:

- the **patched Chrome binary** -> `huligan.ensure_binary()`
- the fingerprint **`.conf`** referenced by `HULIGAN_CONFIG_PATH`
- `--no-sandbox` + the JA4/TLS pins -> `huligan.get_default_stealth_args()`

None of that is specific to any driver, so every tool integrates through one of two
universal shapes.

## Pattern 1 - CDP connect (recommended, highest fidelity)

Launch the fully-wired browser with `huligan.launch_persistent(...)` (or the async
`huligan.Browser`) and hand its `.cdp_url` to any tool that speaks "connect over CDP".
The SDK does proxy forwarding, GeoIP timezone/language, WebRTC spoofing, and the JA4
pins for you.

-> [`cdp_connect_external_framework.py`](cdp_connect_external_framework.py)

## Pattern 2 - binary path + args (for driver-owned tools)

For Selenium / undetected-chromedriver and anything that spawns Chrome itself: point it
at `ensure_binary()`, add `get_default_stealth_args()`, and set `HULIGAN_CONFIG_PATH` to
a generated `.conf`. You own the `--user-data-dir` and the debugging port.

-> [`selenium_binary_and_args.py`](selenium_binary_and_args.py)

## Which should I use?

- Need proxy + GeoIP + WebRTC wired automatically, or rich CDP / JS injection? **Pattern 1.**
  Patch `05_cdp_stealth` isolates the CDP main world, so Pattern 1 is the tested path for
  JS-heavy automation.
- Already invested in a Selenium / chromedriver stack? **Pattern 2**, and add proxy / GeoIP
  flags yourself if you need them.

> **Fingerprint verdicts:** read the **headed** window yourself. The CDP scraper can report
> a stale "100%"; an operator's visual check is authoritative.
