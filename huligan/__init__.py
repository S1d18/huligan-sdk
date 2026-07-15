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
from .installer import (
    ensure_chrome,
    ensure_binary,
    resolve_version,
    latest_version,
    is_installed,
    IncompatibleBuildError,
)
from .conf_spec import CONF_SCHEMA_VERSION
from .profile_bundle import (
    extract_profile_bundle,
    read_profile_bundle,
    write_profile_bundle,
)
from .launch_plan import build_launch_plan, get_default_stealth_args
from .persistent import launch_persistent, LaunchSession, LaunchResult

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

# Agents / scraping pool — requires huligan[agents]
_HAS_AGENTS = False
try:
    from .agents import HuliganBrowserPlugin, HuliganBrowserController, HuliganAgent
    # Only mark available if the import didn't fall back to the
    # `_missing` stub inside agents/__init__.py.
    from .agents import _AVAILABLE as _HAS_AGENTS
except ImportError:
    pass

# HTML → Markdown for LLM agents — requires huligan[markdown]
_HAS_MARKDOWN = False
try:
    from .markdown import extract_markdown, MarkdownExtractor
    from .markdown import _AVAILABLE as _HAS_MARKDOWN
except ImportError:
    pass

# CAPTCHA solver wrappers — requires huligan[captcha]
_HAS_CAPTCHA = False
try:
    from .captcha import CaptchaSolver, CaptchaSolveError
    from .captcha import _AVAILABLE as _HAS_CAPTCHA
except ImportError:
    pass

# Vision-LLM agent — requires huligan[vision]
_HAS_VISION = False
try:
    from .vision import VisionAgent, VisionAgentError
    from .vision import _AVAILABLE as _HAS_VISION
except ImportError:
    pass

# MCP server — expose the antidetect Browser to Claude Desktop / any
# MCP-compatible host as tools — requires huligan[mcp]
_HAS_MCP = False
try:
    from .mcp import run as run_mcp_server
    from .mcp import _AVAILABLE as _HAS_MCP
except ImportError:
    pass

__version__ = "1.3.0"
__all__ = [
    "Browser",
    "launch_persistent",
    "LaunchSession",
    "LaunchResult",
    "build_launch_plan",
    "get_default_stealth_args",
    "FingerprintGenerator",
    "FingerprintProfile",
    "GeoIPManager",
    "GeoIPResult",
    "ProxyForwarder",
    "parse_proxy_string",
    "find_chrome",
    "ensure_chrome",
    "ensure_binary",
    "resolve_version",
    "latest_version",
    "is_installed",
    "IncompatibleBuildError",
    "CONF_SCHEMA_VERSION",
    "extract_profile_bundle",
    "read_profile_bundle",
    "write_profile_bundle",
]
if _HAS_MOUSE_KB:
    __all__ += ["human_like_mouse_click", "human_like_type", "human_like_hotkey"]
if _HAS_SCROLL_IDLE:
    __all__ += [
        "human_like_scroll", "human_like_scroll_to_top",
        "idle_mouse_movement", "simulated_reading_pause",
    ]
if _HAS_AGENTS:
    __all__ += ["HuliganBrowserPlugin", "HuliganBrowserController", "HuliganAgent"]
if _HAS_MARKDOWN:
    __all__ += ["extract_markdown", "MarkdownExtractor"]
if _HAS_CAPTCHA:
    __all__ += ["CaptchaSolver", "CaptchaSolveError"]
if _HAS_VISION:
    __all__ += ["VisionAgent", "VisionAgentError"]
if _HAS_MCP:
    __all__ += ["run_mcp_server"]
