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

# Human-like mouse/keyboard automation (CDP-compatible) — optional dependency
try:
    from .automation.mouse import human_like_mouse_click
    from .automation.keyboard import human_like_type, human_like_hotkey
    _HAS_AUTOMATION = True
except ImportError:
    _HAS_AUTOMATION = False  # Optional dependency — automation helpers not available

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
if _HAS_AUTOMATION:
    __all__ += ["human_like_mouse_click", "human_like_type", "human_like_hotkey"]
