"""
Huligan Antidetect Browser SDK

Usage:
    from huligan import Browser

    async with Browser(proxy="socks5://user:pass@ip:port") as browser:
        page = await browser.new_page()
        await page.goto("https://example.com")
"""

from .browser import Browser
from .fingerprint import FingerprintGenerator, FingerprintProfile
from .geoip import GeoIPManager, GeoIPResult
from .proxy import ProxyForwarder, parse_proxy_string
from .chrome import find_chrome
from .installer import ensure_chrome

# Human-like automation helpers (CDP-compatible). Each block is
# imported independently — installing pip extras only for the helpers
# you actually use is fine.

_HAS_MOUSE_KB = False
try:
    from .automation.mouse import human_like_mouse_click
    from .automation.keyboard import human_like_type, human_like_hotkey
    _HAS_MOUSE_KB = True
except ImportError:
    pass  # Needs huligan[automation] (pytweening, loguru)

_HAS_SCROLL_IDLE = False
try:
    from .automation.scroll import human_like_scroll, human_like_scroll_to_top
    from .automation.idle import idle_mouse_movement, simulated_reading_pause
    _HAS_SCROLL_IDLE = True
except ImportError:
    pass  # Needs only playwright; should always succeed if huligan[playwright] is installed

__version__ = "1.0.0"
__all__ = [
    "Browser",
    "FingerprintGenerator",
    "FingerprintProfile",
    "GeoIPManager",
    "GeoIPResult",
    "ProxyForwarder",
    "parse_proxy_string",
    "find_chrome",
    "ensure_chrome",
]
if _HAS_MOUSE_KB:
    __all__ += ["human_like_mouse_click", "human_like_type", "human_like_hotkey"]
if _HAS_SCROLL_IDLE:
    __all__ += [
        "human_like_scroll", "human_like_scroll_to_top",
        "idle_mouse_movement", "simulated_reading_pause",
    ]
