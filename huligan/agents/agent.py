"""
HuliganAgent — preconfigured agent that wires one or more
HuliganBrowserPlugins into a browser pool.

Two construction modes:

  1) Single-fingerprint agent — pass any combination of proxy,
     profile_path, fingerprint_seed, etc. directly:

         agent = HuliganAgent(
             proxy="socks5://user:pass@host:port",
             fingerprint_seed=12345,
         )

  2) Multi-fingerprint pool — pass a list of plugin configs and
     the pool will round-robin across them:

         agent = HuliganAgent.from_pool([
             {"proxy": "socks5://p1...", "fingerprint_seed": 1},
             {"proxy": "socks5://p2...", "fingerprint_seed": 2},
             {"proxy": "socks5://p3...", "fingerprint_seed": 3},
         ])

In both cases:

  - The framework's stock ``fingerprint_generator`` is disabled
    because huligan handles fingerprint at the C++ patch layer.
    Re-enabling it would cause Playwright to override UA/headers
    and create an inconsistency.
  - ``headless=True`` is the default; pass ``headless=False`` to
    watch.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Dict, Any

from ._runtime import BrowserPool, UpstreamAgentBase
from .plugin import HuliganBrowserPlugin


class HuliganAgent(UpstreamAgentBase):
    """Drop-in agent that uses huligan-patched Chromium."""

    def __init__(
        self,
        *,
        proxy: Optional[str] = None,
        profile_path: Optional[str] = None,
        fingerprint: Optional[dict] = None,
        fingerprint_seed: Optional[int] = None,
        timezone: Optional[str] = None,
        language: Optional[str] = None,
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
        max_open_pages_per_browser: int = 1,
        **agent_kwargs,
    ):
        plugin = HuliganBrowserPlugin(
            proxy=proxy,
            profile_path=profile_path,
            fingerprint=fingerprint,
            fingerprint_seed=fingerprint_seed,
            timezone=timezone,
            language=language,
            headless=headless,
            user_data_dir=user_data_dir,
            extra_args=extra_args,
            max_open_pages_per_browser=max_open_pages_per_browser,
        )
        super().__init__(
            browser_pool=BrowserPool(plugins=[plugin]),
            # Stock fingerprint_generator would conflict with
            # huligan's C++ patches — explicit None.
            fingerprint_generator=None,
            **agent_kwargs,
        )

    @classmethod
    def from_pool(
        cls,
        plugin_configs: Sequence[Dict[str, Any]],
        **agent_kwargs,
    ) -> "HuliganAgent":
        """
        Construct an agent whose browser pool round-robins across
        multiple HuliganBrowserPlugin instances. Each dict in
        ``plugin_configs`` is passed verbatim to HuliganBrowserPlugin.

        Args:
            plugin_configs: list of dicts of HuliganBrowserPlugin
                kwargs (proxy, fingerprint_seed, headless, etc).
            **agent_kwargs: forwarded to the upstream base class.

        Returns:
            HuliganAgent instance ready for ``.run([...urls...])``.
        """
        if not plugin_configs:
            raise ValueError("plugin_configs must be a non-empty sequence")
        plugins = [HuliganBrowserPlugin(**cfg) for cfg in plugin_configs]

        # Bypass __init__ to avoid double-constructing a plugin —
        # we already have the list we want.
        instance = cls.__new__(cls)
        UpstreamAgentBase.__init__(
            instance,
            browser_pool=BrowserPool(plugins=plugins),
            fingerprint_generator=None,
            **agent_kwargs,
        )
        return instance
