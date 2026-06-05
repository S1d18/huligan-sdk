"""
Huligan Antidetect Browser — unified entry point.

Usage:
    from huligan import Browser

    # Minimal — just proxy
    async with Browser(proxy="socks5://user:pass@ip:port") as b:
        page = await b.new_page()
        await page.goto("https://example.com")

    # With custom fingerprint
    async with Browser(
        proxy="http://user:pass@ip:port",
        fingerprint={"gpu_vendor_preference": "nvidia", "platform": "Win32"},
    ) as b:
        page = await b.new_page()

    # Without proxy (local)
    async with Browser() as b:
        page = await b.new_page()

    # With pre-made .conf file
    async with Browser(
        proxy="socks5://...",
        profile_path="my_profile.conf"
    ) as b:
        page = await b.new_page()
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Union

from .chrome import find_chrome
from .fingerprint import FingerprintGenerator, FingerprintProfile
from .geoip import GeoIPManager, GeoIPResult
from .launch_plan import (
    build_launch_plan,
    cdp_mode_from_conf,
    find_free_port,
    update_conf_keys,
)
from .proxy import (
    ProxyForwarder,
    parse_proxy_string,
    detect_exit_ip,
    detect_local_public_ip,
)

log = logging.getLogger("huligan.browser")


class Browser:
    """
    Huligan Antidetect Browser — single entry point for launching
    an antidetect browser instance with proxy, fingerprint, and GeoIP.
    """

    def __init__(
        self,
        chrome_path: Union[str, Path, None] = None,
        proxy: Optional[str] = None,
        proxy_type: Optional[str] = None,
        profile_path: Union[str, Path, None] = None,
        fingerprint: Optional[dict] = None,
        timezone: Optional[str] = None,
        language: Optional[str] = None,
        cdp_port: Optional[int] = None,
        headless: bool = False,
        user_data_dir: Union[str, Path, None] = None,
        extra_args: Optional[list] = None,
    ):
        """
        Args:
            chrome_path: Path to chrome.exe (auto-detect if None)
            proxy: Proxy string, e.g. "socks5://user:pass@ip:port" or "ip:port:user:pass"
            proxy_type: "socks5" | "http" (auto-detect from URL if None)
            profile_path: Path to existing .conf file (auto-generate if None)
            fingerprint: Dict of fingerprint params for FingerprintGenerator.generate()
            timezone: Override timezone (otherwise from GeoIP)
            language: Override language (otherwise from GeoIP)
            cdp_port: CDP remote debugging port (auto-assign if None)
            headless: Run in headless mode
            user_data_dir: Chrome user data directory (temp dir if None)
            extra_args: Additional Chrome command-line arguments
        """
        self._chrome_path_input = chrome_path
        self._proxy_str = proxy
        self._proxy_type_override = proxy_type
        self._profile_path_input = profile_path
        self._fingerprint_opts = fingerprint or {}
        self._timezone_override = timezone
        self._language_override = language
        self._cdp_port_input = cdp_port
        self._headless = headless
        self._user_data_dir_input = user_data_dir
        self._extra_args = extra_args or []

        # Runtime state
        self._chrome_path: Optional[Path] = None
        self._profile_path: Optional[Path] = None
        self._profile: Optional[FingerprintProfile] = None
        self._geo: Optional[GeoIPResult] = None
        self._proxy_info: Optional[dict] = None
        self._forwarder: Optional[ProxyForwarder] = None
        self._process: Optional[subprocess.Popen] = None
        self._cdp_port: Optional[int] = None
        self._user_data_dir: Optional[Path] = None
        self._temp_profile: Optional[Path] = None  # auto-generated .conf to clean up
        self._temp_data_dir: Optional[str] = None   # temp user-data-dir to clean up
        self._playwright = None
        self._pw_browser = None

    async def start(self) -> "Browser":
        """
        Launch the browser.

        Steps:
        1. Find Chrome executable
        2. Generate fingerprint + .conf (if no profile_path)
        3. GeoIP lookup (if proxy and no timezone override)
        4. Write timezone/language to .conf
        5. Start proxy forwarder (if proxy has auth)
        6. Launch Chrome subprocess
        7. Wait for CDP ready

        Returns:
            self
        """
        # 1. Find Chrome
        chrome_input = Path(self._chrome_path_input) if self._chrome_path_input else None
        self._chrome_path = find_chrome(explicit_path=chrome_input)
        log.info(f"Chrome: {self._chrome_path}")

        # 2. Parse proxy
        if self._proxy_str:
            self._proxy_info = parse_proxy_string(self._proxy_str)
            if self._proxy_type_override:
                self._proxy_info["type"] = self._proxy_type_override
            log.info(
                f"Proxy: {self._proxy_info['type']}://"
                f"{self._proxy_info['host']}:{self._proxy_info['port']}"
            )

        # 3. Generate fingerprint / use existing profile
        if self._profile_path_input:
            self._profile_path = Path(self._profile_path_input).resolve()
            if not self._profile_path.is_file():
                raise FileNotFoundError(f"Profile not found: {self._profile_path}")
        else:
            gen = FingerprintGenerator()
            self._profile = gen.generate(**self._fingerprint_opts)
            # Write to temp .conf
            fd, tmp_path = tempfile.mkstemp(suffix=".conf", prefix="huligan_")
            os.close(fd)
            self._temp_profile = Path(tmp_path)
            self._temp_profile.write_text(self._profile.to_conf(), encoding="utf-8")
            self._profile_path = self._temp_profile
            log.info(f"Generated profile: {self._profile_path}")

        # 4. GeoIP lookup.
        # Resolution strategy:
        #   - With proxy: GeoIP the proxy host (presents location of the
        #     exit IP to remote sites, which is what we want to match).
        #   - Without proxy: the machine *is* the exit. Probe the local
        #     public IP and GeoIP that — otherwise timezone/languages
        #     fall back to whatever the .conf default carries, which
        #     mismatches the IP the page actually sees (a strong bot
        #     signal: "IP says Moscow but Accept-Language is en-US").
        # User overrides (timezone / language kwargs) skip the lookup
        # for that field but the IP-probe still runs so 4b can spoof.
        public_ip_for_geo: Optional[str] = None
        if self._proxy_info:
            public_ip_for_geo = self._proxy_info["host"]
        else:
            try:
                public_ip_for_geo = detect_local_public_ip(timeout=4.0)
                if public_ip_for_geo:
                    log.info(f"No proxy — resolved local public IP for GeoIP: {public_ip_for_geo}")
            except Exception as e:
                log.warning(f"Local public IP probe failed: {e}")

        if public_ip_for_geo and not self._timezone_override:
            try:
                manager = GeoIPManager()
                self._geo = manager.lookup(public_ip_for_geo)
                manager.close()
                if self._geo.error:
                    log.warning(f"GeoIP error: {self._geo.error}")
                    self._geo = None
                else:
                    log.info(f"GeoIP: {self._geo}")
            except Exception as e:
                log.warning(f"GeoIP failed: {e}")

        # 4b. WebRTC local-IP spoof.
        # With proxy: spoof to the proxy's exit IP (matches what page JS
        # observes through any non-WebRTC channel). Without proxy: spoof
        # to the machine's own public IP — prevents the LAN-IP leak
        # (192.168.x.x / 10.x.x.x) WebRTC otherwise gathers as host
        # candidates. Profile-supplied value always wins.
        self._webrtc_spoof_ip: Optional[str] = None
        existing = ""
        if self._profile is not None:
            existing = getattr(self._profile, "webrtc_local_ipv4", "") or ""
        if existing:
            self._webrtc_spoof_ip = existing
            log.info(f"WebRTC spoof IPv4: {existing} (from profile)")
        elif self._proxy_info:
            exit_ip = detect_exit_ip(self._proxy_info, timeout=4.0)
            if exit_ip:
                self._webrtc_spoof_ip = exit_ip
                log.info(f"WebRTC spoof IPv4: {exit_ip}")
            else:
                log.info("WebRTC exit-IP probe yielded no result; spoof disabled")
        elif public_ip_for_geo:
            self._webrtc_spoof_ip = public_ip_for_geo
            log.info(f"WebRTC spoof IPv4: {public_ip_for_geo} (local public)")

        if (
            self._webrtc_spoof_ip
            and not existing
            and self._profile is not None
        ):
            self._profile.webrtc_local_ipv4 = self._webrtc_spoof_ip
            # Rewrite the temp .conf with the freshly detected value
            # before Chrome opens it.
            if self._temp_profile is not None:
                self._temp_profile.write_text(
                    self._profile.to_conf(), encoding="utf-8"
                )

        # 5. Update .conf with timezone/language
        timezone = self._timezone_override
        language = self._language_override

        if self._geo and not timezone:
            timezone = self._geo.timezone
        if self._geo and not language:
            # Expand GeoIP language to include en-US,en (Dolphin Anty parity)
            geo_lang = self._geo.language or "en-US"
            parts = [p.strip() for p in geo_lang.split(",") if p.strip()]
            if "en-US" not in parts:
                parts.append("en-US")
            if "en" not in parts:
                parts.append("en")
            language = ",".join(parts)

        if timezone or language:
            self._update_conf(timezone, language)

        # 6. Start proxy forwarder (if auth needed)
        if self._proxy_info and self._proxy_info["user"] and self._proxy_info["password"]:
            self._forwarder = ProxyForwarder(
                upstream_host=self._proxy_info["host"],
                upstream_port=self._proxy_info["port"],
                upstream_user=self._proxy_info["user"],
                upstream_pass=self._proxy_info["password"],
                upstream_type=self._proxy_info["type"],
            )
            local_port = await self._forwarder.start()
            log.info(f"Forwarder ready on 127.0.0.1:{local_port}")

        # 7. Assign CDP port
        if self._cdp_port_input is not None:
            self._cdp_port = self._cdp_port_input
        else:
            self._cdp_port = self._find_free_port()

        # 8. Resolve user-data-dir (temp dir is tracked for cleanup in close()).
        if self._user_data_dir_input:
            self._user_data_dir = Path(self._user_data_dir_input)
        else:
            self._temp_data_dir = tempfile.mkdtemp(prefix="huligan_")
            self._user_data_dir = Path(self._temp_data_dir)

        # 9. Build Chrome args + env through the shared launch-plan builder.
        # This is the SINGLE source of truth (proxy-server selection,
        # host-resolver/WebRTC leak flags, language flags, HULIGAN_CONFIG_PATH,
        # TZ, HULIGAN_CDP_MODE) — reused verbatim by huligan.launch_persistent
        # so the GUI path can never drift from the anti-detect contract.
        chrome_args, env = build_launch_plan(
            chrome_path=self._chrome_path,
            profile_path=self._profile_path,
            cdp_port=self._cdp_port,
            user_data_dir=self._user_data_dir,
            forwarder_port=self._forwarder.port if self._forwarder else None,
            proxy_info=self._proxy_info,
            webrtc_spoof_ip=self._webrtc_spoof_ip,
            language=language,
            timezone=timezone,
            cdp_mode=cdp_mode_from_conf(self._profile_path),
            headless=self._headless,
            extra_args=self._extra_args,
        )

        # 10. Launch Chrome
        self._process = subprocess.Popen(chrome_args, env=env)
        log.info(f"Chrome started (PID: {self._process.pid}, CDP: {self._cdp_port})")

        # 11. Wait for CDP to be ready
        await self._wait_for_cdp()

        return self

    @staticmethod
    def _cdp_mode_from_conf(profile_path) -> Optional[str]:
        """Back-compat shim — delegates to :func:`launch_plan.cdp_mode_from_conf`."""
        return cdp_mode_from_conf(profile_path)

    async def new_page(self):
        """
        Create a new page via CDP using playwright.

        Returns:
            Page object (playwright.async_api.Page or playwright.async_api.Page)
        """
        if self._pw_browser is None:
            self._pw_browser = await self._connect_playwright()

        context = self._pw_browser.contexts[0] if self._pw_browser.contexts else await self._pw_browser.new_context()
        page = await context.new_page()
        return page

    async def _cookie_page(self):
        """Reuse an existing page (or open a throwaway one) for cookie CDP ops."""
        if self._pw_browser is None:
            self._pw_browser = await self._connect_playwright()
        ctx = self._pw_browser.contexts[0] if self._pw_browser.contexts else await self._pw_browser.new_context()
        return ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def export_cookies(self, path, *, page=None, domains=None) -> int:
        """Export this profile's cookies to a portable JSON bundle.

        Uses CDP (evaluate-free, captures httpOnly). Returns the count written.
        See ``huligan.cookies`` / ``docs/COOKIES.md``.
        """
        from . import cookies as _cookies
        page = page or await self._cookie_page()
        return await _cookies.export_cookies_from_page(page, path, domains=domains)

    async def import_cookies(self, path, *, page=None, clear_existing=False) -> int:
        """Load cookies from a bundle into this profile (before navigating).

        Returns the count loaded.
        """
        from . import cookies as _cookies
        page = page or await self._cookie_page()
        return await _cookies.import_cookies_to_page(page, path, clear_existing=clear_existing)

    async def close(self):
        """Close browser, forwarder, and clean up temp files."""
        # Close playwright connection
        if self._pw_browser:
            try:
                await self._pw_browser.close()
            except Exception:
                pass
            self._pw_browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        # Terminate Chrome
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            log.info("Chrome stopped")
        self._process = None

        # Stop forwarder
        if self._forwarder:
            await self._forwarder.stop()
            self._forwarder = None

        # Clean up temp profile
        if self._temp_profile and self._temp_profile.exists():
            try:
                self._temp_profile.unlink()
            except Exception:
                pass

        # Clean up temp data dir
        if self._temp_data_dir:
            import shutil
            try:
                shutil.rmtree(self._temp_data_dir, ignore_errors=True)
            except Exception:
                pass

    async def __aenter__(self) -> "Browser":
        return await self.start()

    async def __aexit__(self, *args):
        await self.close()

    @property
    def cdp_url(self) -> str:
        """CDP WebSocket URL for connecting automation tools."""
        return f"http://127.0.0.1:{self._cdp_port}"

    @property
    def cdp_port(self) -> Optional[int]:
        """CDP remote debugging port."""
        return self._cdp_port

    @property
    def fingerprint_profile(self) -> Optional[FingerprintProfile]:
        """The generated fingerprint profile (None if using existing .conf)."""
        return self._profile

    @property
    def geo(self) -> Optional[GeoIPResult]:
        """GeoIP result (None if no proxy or GeoIP failed)."""
        return self._geo

    @property
    def profile_path(self) -> Optional[Path]:
        """Path to the .conf file being used."""
        return self._profile_path

    @property
    def pid(self) -> Optional[int]:
        """Chrome process ID."""
        return self._process.pid if self._process else None

    def _update_conf(self, timezone: Optional[str], language: Optional[str]):
        """Update the .conf file with timezone, language, geolocation, and mode fields.

        Builds the update set from the resolved GeoIP/override state, then
        delegates the line-rewrite to :func:`launch_plan.update_conf_keys` so the
        file algorithm lives in exactly one place (shared with the persistent
        launcher).
        """
        if not self._profile_path:
            return

        updates = {}
        if timezone:
            updates["timezone"] = timezone
            # mode: "auto" if timezone came from GeoIP, "manual" if from user override
            updates["timezone_mode"] = "manual" if self._timezone_override else "auto"
        if language:
            updates["languages"] = language
            updates["language_mode"] = "manual" if self._language_override else "auto"

        if self._geo:
            updates["geolocation_latitude"] = str(self._geo.latitude)
            updates["geolocation_longitude"] = str(self._geo.longitude)
            updates["geolocation_accuracy"] = str(int(self._geo.accuracy))
            updates["geolocation_mode"] = "auto"

        update_conf_keys(self._profile_path, updates)

    async def _wait_for_cdp(self, timeout: float = 15.0):
        """Wait for Chrome CDP to become available."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self._cdp_port}/json/version")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read())
                    if data.get("webSocketDebuggerUrl"):
                        log.info("CDP ready")
                        return
            except Exception:
                pass

            # Check if process died
            if self._process and self._process.poll() is not None:
                raise RuntimeError(
                    f"Chrome exited unexpectedly (code: {self._process.returncode})"
                )

            await asyncio.sleep(0.3)

        raise TimeoutError(f"CDP not ready after {timeout}s on port {self._cdp_port}")

    async def _connect_playwright(self):
        """Connect to Chrome via CDP using playwright."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright is not installed. Install it with:\n"
                "  pip install huligan[playwright]   (or: pip install playwright)"
            )
        self._playwright = await async_playwright().start()
        browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
        log.info("Connected via playwright")
        return browser

    @staticmethod
    def _find_free_port() -> int:
        """Find a free TCP port (delegates to :func:`launch_plan.find_free_port`)."""
        return find_free_port()
