"""
HuliganBrowserPlugin — plugin that boots Huligan Chrome through the
standard huligan.Browser launch flow.

We reuse ``huligan.Browser`` internally so proxy forwarder, GeoIP,
.conf generation, and CDP port assignment behave identically to
direct SDK usage. The plugin's only job is to bridge that boot
sequence into the browser-pool lifecycle expected by the upstream
agents framework.
"""

from __future__ import annotations

import logging
from typing import Optional

from ._runtime import UpstreamBrowserPlugin, UpstreamBrowserController
from ..browser import Browser

log = logging.getLogger("huligan.agents.plugin")


class HuliganBrowserController(UpstreamBrowserController):
    """
    Wraps the upstream browser controller so that closing the
    controller also tears down the underlying huligan Browser
    (Chrome subprocess, ProxyForwarder, temp files).

    The browser pool calls close() on the controller when retiring a
    browser from the pool. Without this hook, Chrome processes would
    leak.
    """

    def __init__(self, huligan_browser: Browser, **kwargs):
        super().__init__(**kwargs)
        self._huligan_browser = huligan_browser

    async def close(self) -> None:  # type: ignore[override]
        # Best-effort upstream close first
        try:
            await super().close()  # type: ignore[misc]
        except Exception as e:
            log.warning(f"upstream controller close failed: {e}")
        # Always clean up our subprocess + forwarder
        try:
            await self._huligan_browser.close()
        except Exception as e:
            log.warning(f"Huligan Browser.close failed: {e}")


class HuliganBrowserPlugin(UpstreamBrowserPlugin):
    """
    Boot a Huligan-patched Chromium for each browser the pool
    requests, and surface it through a Playwright browser controller
    so the upstream agents framework can manage pages and lifecycle.

    Parameters mirror ``huligan.Browser`` and are applied to every
    instance the pool creates from this plugin. Provide one plugin
    per fingerprint/proxy combination if you want diversity in the
    pool (see HuliganAgent.from_pool).

    Args:
        proxy: huligan proxy string (e.g. "socks5://user:pass@host:port").
        profile_path: Path to an existing .conf. If None, huligan
            auto-generates one from ``fingerprint`` or from a seed.
        fingerprint: Dict of FingerprintGenerator.generate() kwargs
            (platform, gpu_vendor_preference).
        fingerprint_seed: Convenience integer — when set, the plugin
            builds the profile via FingerprintProfile.from_seed(seed).
            Mutually exclusive with profile_path.
        timezone / language: Manual overrides; bypasses GeoIP.
        headless: Run Chrome in headless=new mode. Default True for
            scraping; flip to False to watch a session.
        user_data_dir: Persistent profile directory. If None, huligan
            uses a temp dir wiped on close.
        extra_args: Extra Chrome CLI flags to append.
        max_open_pages_per_browser: Pool setting — how many tabs
            can share one Chrome instance. Default 1 (safest for
            stealth — one identity per process). Increase for
            throughput when stealth tolerance is high.
    """

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
        extra_args: Optional[list] = None,
        max_open_pages_per_browser: int = 1,
        **playwright_plugin_kwargs,
    ):
        super().__init__(**playwright_plugin_kwargs)

        if profile_path and fingerprint_seed is not None:
            raise ValueError(
                "Pass either profile_path OR fingerprint_seed, not both."
            )

        # If a seed was given, materialise it into a .conf so we go
        # through the same code path as profile_path.
        if fingerprint_seed is not None:
            import tempfile
            from pathlib import Path
            from ..fingerprint import FingerprintProfile

            platform = (fingerprint or {}).get("platform", "Win32")
            gpu = (fingerprint or {}).get("gpu_vendor_preference")
            profile = FingerprintProfile.from_seed(
                seed=fingerprint_seed,
                platform=platform,
                gpu_vendor_preference=gpu,
            )
            fd_path = Path(tempfile.mkstemp(suffix=".conf", prefix="huligan_agents_")[1])
            fd_path.write_text(profile.to_conf(), encoding="utf-8")
            profile_path = str(fd_path)

        self._huligan_kwargs = {
            "proxy": proxy,
            "profile_path": profile_path,
            "fingerprint": fingerprint,
            "timezone": timezone,
            "language": language,
            "headless": headless,
            "user_data_dir": user_data_dir,
            "extra_args": extra_args,
        }
        self._max_open_pages = max_open_pages_per_browser

    async def new_browser(self) -> UpstreamBrowserController:
        # Boot a Huligan Browser via the standard SDK flow. That
        # handles proxy parsing, GeoIP, .conf generation, forwarder,
        # CDP port, Chrome subprocess, and CDP connection — i.e.
        # everything that distinguishes huligan from a vanilla Chrome.
        hb = Browser(**{k: v for k, v in self._huligan_kwargs.items() if v is not None})
        await hb.start()

        # Connect Playwright over CDP to the running browser. The
        # Browser class lazy-connects on .new_page(); we trigger it
        # explicitly so we have a Playwright Browser handle to give
        # the controller.
        pw_browser = await hb._connect_playwright()  # noqa: SLF001 — internal API

        return HuliganBrowserController(
            huligan_browser=hb,
            browser=pw_browser,
            max_open_pages_per_browser=self._max_open_pages,
            # IMPORTANT: header_generator=None — huligan applies UA
            # and client-hints at the C++ patch layer. Letting the
            # upstream framework rewrite them via Playwright context
            # options would split the fingerprint.
            header_generator=None,
        )
