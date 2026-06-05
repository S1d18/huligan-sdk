"""Synchronous, persistent (detached) launch of the Huligan browser.

The async :class:`huligan.browser.Browser` is built for *automation*: it is an
async context manager that connects Playwright over CDP and **terminates Chrome
on exit**. A desktop GUI (PySide6) needs the opposite shape — a browser the user
drives by hand that:

  * is launched from **synchronous** code (no event loop on the calling thread),
  * **stays alive** after the launch call returns,
  * does **not** require a Playwright connection,
  * still gets the full anti-detect launch contract (auth-proxy forwarder,
    WebRTC/DNS leak flags, GeoIP timezone/language, ``HULIGAN_CDP_MODE``).

:func:`launch_persistent` provides exactly that. It reuses
:func:`huligan.launch_plan.build_launch_plan` (the same argv/env builder the
async ``Browser`` uses, so the two can never drift) and solves the one hard
problem the GUI cannot: the :class:`huligan.proxy.ProxyForwarder` is an asyncio
server, but the caller is synchronous and the forwarder must outlive the call.
We run a dedicated daemon thread hosting its own event loop for the forwarder's
lifetime, and tear it down from :meth:`LaunchResult.stop`.

Example::

    from huligan import launch_persistent

    session = launch_persistent(
        profile_path="~/.huligan_profiles/acc1.conf",
        proxy="socks5://user:pass@1.2.3.4:1080",
        proxy_type="socks5",
        user_data_dir="~/.huligan_profiles/acc1",
        url="https://browserscan.net",
    )
    print(session.pid, session.cdp_url)
    ...
    session.stop()   # terminates Chrome + tears down the forwarder + loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional, Union

from .chrome import find_chrome
from .geoip import GeoIPManager
from .launch_plan import (
    build_launch_plan,
    cdp_mode_from_conf,
    find_free_port,
    read_conf_value,
    update_conf_keys,
)
from .proxy import (
    ProxyForwarder,
    detect_exit_ip,
    detect_local_public_ip,
    parse_proxy_string,
)

log = logging.getLogger("huligan.persistent")


class _BackgroundLoop:
    """A daemon thread running a private asyncio event loop.

    Lets synchronous code own an asyncio resource (here, the SOCKS5 forwarder)
    for an arbitrary lifetime. Coroutines are submitted with :meth:`run_coro`
    (blocking, thread-safe). :meth:`shutdown` stops the loop and joins the
    thread, draining any still-pending tasks first.
    """

    def __init__(self, start_timeout: float = 5.0):
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="huligan-persistent-loop", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=start_timeout):
            raise RuntimeError("Background event loop failed to start")

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        try:
            self._loop.run_forever()
        finally:
            # Loop was stopped; cancel + drain leftovers, then close.
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            self._loop.close()

    def run_coro(self, coro, timeout: Optional[float] = None):
        """Submit a coroutine to the loop and block for its result."""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout)

    @property
    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def shutdown(self, timeout: float = 5.0) -> None:
        if not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout)


class LaunchResult:
    """Handle to a running, persistent Huligan browser.

    Quacks like a :class:`subprocess.Popen` for the attributes a GUI tracks
    (``pid``, :meth:`poll`, :meth:`terminate`, :meth:`kill`, :meth:`wait`) so it
    can be dropped into existing process-tracking code with minimal change.
    Arbitrary attributes (e.g. a GUI log handle) may be attached freely.

    Call :meth:`stop` (or use the object as a context manager) to terminate
    Chrome and tear down the proxy forwarder + background loop.
    """

    def __init__(
        self,
        *,
        process: subprocess.Popen,
        cdp_port: int,
        profile_path: Path,
        user_data_dir: Path,
        forwarder: Optional[ProxyForwarder] = None,
        bgloop: Optional[_BackgroundLoop] = None,
        webrtc_spoof_ip: Optional[str] = None,
        geo=None,
        temp_conf: Optional[Path] = None,
    ):
        self.process = process
        self._cdp_port = cdp_port
        # The user's SAVED profile path (identity); never mutated under the
        # default conf_geo="copy". temp_conf, if set, is the throwaway copy the
        # binary actually reads — deleted on stop().
        self.profile_path = profile_path
        self.user_data_dir = user_data_dir
        self.temp_conf = temp_conf
        self._forwarder = forwarder
        self._bgloop = bgloop
        self.webrtc_spoof_ip = webrtc_spoof_ip
        self.geo = geo
        self._stopped = False
        # GUI glue may attach these; kept here so the contract is explicit.
        self._log_handle = None
        self._log_file = None

    # --- Popen-compatible surface ---------------------------------------
    @property
    def pid(self) -> Optional[int]:
        return self.process.pid if self.process else None

    def poll(self) -> Optional[int]:
        """Return Chrome's exit code, or ``None`` while still running."""
        return self.process.poll() if self.process else None

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        return self.process.wait(timeout) if self.process else None

    def terminate(self) -> None:
        """Terminate Chrome AND tear down the forwarder/loop (full cleanup)."""
        self.stop()

    def kill(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.kill()
        self._teardown_proxy()

    # --- session lifecycle ----------------------------------------------
    @property
    def cdp_port(self) -> int:
        return self._cdp_port

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self._cdp_port}"

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate Chrome, then stop the forwarder and background loop.

        Idempotent and non-blocking beyond ``timeout``. Safe to call from a GUI
        thread.
        """
        if self._stopped:
            return
        self._stopped = True

        # 1. Terminate Chrome.
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            except Exception as e:
                log.warning(f"Error terminating Chrome: {e}")

        # 2. Tear down forwarder + loop.
        self._teardown_proxy(timeout=timeout)

        # 3. Remove the temp .conf copy (conf_geo="copy"); the binary no longer
        # needs it once Chrome is gone.
        if self.temp_conf is not None:
            try:
                self.temp_conf.unlink()
            except OSError:
                pass
            self.temp_conf = None

        # 4. Close any GUI-attached log handle.
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def _teardown_proxy(self, timeout: float = 5.0) -> None:
        if self._forwarder is not None and self._bgloop is not None:
            try:
                self._bgloop.run_coro(self._forwarder.stop(), timeout=timeout)
            except Exception as e:
                log.debug(f"Forwarder stop error (ignored): {e}")
            self._forwarder = None
        if self._bgloop is not None:
            try:
                self._bgloop.shutdown(timeout=timeout)
            except Exception:
                pass
            self._bgloop = None

    def __enter__(self) -> "LaunchResult":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def __repr__(self) -> str:
        return (
            f"LaunchResult(pid={self.pid}, cdp_port={self._cdp_port}, "
            f"profile={self.profile_path.name if self.profile_path else None})"
        )


def launch_persistent(
    *,
    profile_path: Union[str, Path],
    proxy: Optional[str] = None,
    proxy_type: Optional[str] = None,
    cdp_port: Optional[int] = None,
    user_data_dir: Union[str, Path, None] = None,
    url: Optional[str] = None,
    timezone: Optional[str] = None,
    language: Optional[str] = None,
    chrome_path: Union[str, Path, None] = None,
    headless: bool = False,
    extra_args: Optional[list] = None,
    geoip: bool = True,
    conf_geo: str = "copy",
    wait_for_cdp: bool = False,
    cdp_timeout: float = 15.0,
    popen_kwargs: Optional[dict] = None,
) -> LaunchResult:
    """Launch a persistent, user-driven Huligan browser from synchronous code.

    Mirrors the resolution that :meth:`Browser.start` performs (proxy parse →
    GeoIP → WebRTC exit-IP → conf update → forwarder → argv/env), but returns a
    detached :class:`LaunchResult` that does NOT auto-close and needs no
    Playwright connection.

    Args:
        profile_path: Path to the .conf to launch (must exist).
        proxy: Proxy string in any format ``parse_proxy_string`` accepts.
        proxy_type: Force ``"socks5"`` | ``"http"``. **Pass this from a GUI
            profile** — ``parse_proxy_string`` defaults to ``socks5`` for
            ``host:port`` strings, while the GUI stores the protocol separately.
        cdp_port: Remote debugging port (auto free port if ``None``).
        user_data_dir: Chrome profile dir. If ``None`` a temp dir is created
            (NOT auto-removed — the browser outlives this call; the caller owns
            cleanup). A GUI should always pass an explicit per-profile dir.
        url: Optional start URL.
        timezone: Force timezone (else GeoIP). Pass when the GUI mode is manual.
        language: Force Accept-Language (else GeoIP). Pass when mode is manual.
        chrome_path: Explicit chrome path (auto-detect if ``None``).
        headless: ``--headless=new``.
        extra_args: Extra Chrome flags.
        geoip: Run GeoIP/exit-IP probes (set ``False`` to skip all network probes).
        conf_geo: How resolved timezone/language/geolocation/``webrtc_local_ipv4``
            reach the binary. The user's saved profile is treated as a template:
              ``"copy"`` (default) — launch from a TEMP COPY of the .conf with the
                values applied; the saved profile is never mutated (the temp copy
                is deleted by :meth:`LaunchResult.stop`).
              ``"inplace"`` — write the values into the saved .conf (legacy).
              ``"off"`` — write nothing; timezone rides ``TZ`` env and language the
                ``--accept-lang`` flag only (no geolocation/WebRTC conf spoof).
        wait_for_cdp: Block until the CDP endpoint answers (up to ``cdp_timeout``).
            Default ``False`` (fire-and-forget, matching a GUI launch).
        cdp_timeout: Seconds to wait when ``wait_for_cdp`` is True.
        popen_kwargs: Extra kwargs splatted into ``subprocess.Popen`` — a GUI
            passes ``creationflags`` (e.g. ``CREATE_NO_WINDOW``) and
            ``stdout``/``stderr`` log handles here.

    Returns:
        :class:`LaunchResult`.
    """
    if conf_geo not in ("copy", "inplace", "off"):
        raise ValueError(f"conf_geo must be 'copy', 'inplace' or 'off', got {conf_geo!r}")

    profile_path = Path(profile_path).expanduser().resolve()
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_path}")

    chrome = find_chrome(explicit_path=Path(chrome_path).expanduser() if chrome_path else None)
    log.info(f"Chrome: {chrome}")

    # --- parse proxy ----------------------------------------------------
    proxy_info = None
    if proxy:
        proxy_info = parse_proxy_string(proxy)
        if proxy_type:
            proxy_info["type"] = proxy_type
        log.info(f"Proxy: {proxy_info['type']}://{proxy_info['host']}:{proxy_info['port']}")

    # --- GeoIP (sync) ---------------------------------------------------
    geo = None
    public_ip_for_geo: Optional[str] = None
    if geoip:
        if proxy_info:
            public_ip_for_geo = proxy_info["host"]
        else:
            try:
                public_ip_for_geo = detect_local_public_ip(timeout=4.0)
            except Exception as e:
                log.warning(f"Local public IP probe failed: {e}")
        if public_ip_for_geo and not timezone:
            try:
                mgr = GeoIPManager()
                geo = mgr.lookup(public_ip_for_geo)
                mgr.close()
                if getattr(geo, "error", None):
                    log.warning(f"GeoIP error: {geo.error}")
                    geo = None
                else:
                    log.info(f"GeoIP: {geo}")
            except Exception as e:
                log.warning(f"GeoIP failed: {e}")
                geo = None

    # --- resolve timezone / language (mirror Browser.start) -------------
    tz = timezone
    lang = language
    if geo and not tz:
        tz = geo.timezone
    if geo and not lang:
        geo_lang = geo.language or "en-US"
        parts = [p.strip() for p in geo_lang.split(",") if p.strip()]
        if "en-US" not in parts:
            parts.append("en-US")
        if "en" not in parts:
            parts.append("en")
        lang = ",".join(parts)

    # --- WebRTC spoof IP (sync). A .conf value always wins. -------------
    existing_webrtc = read_conf_value(profile_path, "webrtc_local_ipv4") or ""
    webrtc_spoof_ip: Optional[str] = existing_webrtc or None
    if not webrtc_spoof_ip and geoip:
        if proxy_info:
            webrtc_spoof_ip = detect_exit_ip(proxy_info, timeout=4.0)
            if webrtc_spoof_ip:
                log.info(f"WebRTC spoof IPv4: {webrtc_spoof_ip} (proxy exit)")
        elif public_ip_for_geo:
            webrtc_spoof_ip = public_ip_for_geo
            log.info(f"WebRTC spoof IPv4: {webrtc_spoof_ip} (local public)")

    # --- resolve which .conf the binary will read -----------------------
    # The saved profile is the user's template. Under conf_geo="copy" (default)
    # the per-launch GeoIP/WebRTC values go into a temp COPY that the binary
    # reads and that stop() deletes — the saved file is never mutated.
    updates: dict = {}
    if conf_geo in ("copy", "inplace"):
        if tz:
            updates["timezone"] = tz
            updates["timezone_mode"] = "manual" if timezone else "auto"
        if lang:
            updates["languages"] = lang
            updates["language_mode"] = "manual" if language else "auto"
        if geo:
            updates["geolocation_latitude"] = str(geo.latitude)
            updates["geolocation_longitude"] = str(geo.longitude)
            updates["geolocation_accuracy"] = str(int(geo.accuracy))
            updates["geolocation_mode"] = "auto"
        if webrtc_spoof_ip and not existing_webrtc:
            updates["webrtc_local_ipv4"] = webrtc_spoof_ip

    launch_conf_path = profile_path
    temp_conf: Optional[Path] = None
    if conf_geo == "inplace":
        update_conf_keys(profile_path, updates)
    elif conf_geo == "copy" and updates:
        fd, tmp = tempfile.mkstemp(suffix=".conf", prefix="huligan_launch_")
        os.close(fd)
        temp_conf = Path(tmp)
        shutil.copyfile(profile_path, temp_conf)
        update_conf_keys(temp_conf, updates)
        launch_conf_path = temp_conf
        log.info(f"Launching from temp .conf copy (saved profile untouched): {temp_conf}")

    # --- proxy forwarder on a background loop (only when auth needed) ----
    bgloop: Optional[_BackgroundLoop] = None
    forwarder: Optional[ProxyForwarder] = None
    forwarder_port: Optional[int] = None
    if proxy_info and proxy_info.get("user") and proxy_info.get("password"):
        bgloop = _BackgroundLoop()
        forwarder = ProxyForwarder(
            upstream_host=proxy_info["host"],
            upstream_port=proxy_info["port"],
            upstream_user=proxy_info["user"],
            upstream_pass=proxy_info["password"],
            upstream_type=proxy_info["type"],
        )
        try:
            forwarder_port = bgloop.run_coro(forwarder.start(), timeout=10.0)
            log.info(f"Forwarder ready on 127.0.0.1:{forwarder_port}")
        except Exception:
            # Roll back the loop if the forwarder failed to bind.
            bgloop.shutdown(timeout=3.0)
            raise

    # --- ports + user-data-dir ------------------------------------------
    if cdp_port is None:
        cdp_port = find_free_port()

    if user_data_dir is not None:
        user_data_dir = Path(user_data_dir).expanduser()
    else:
        user_data_dir = Path(tempfile.mkdtemp(prefix="huligan_"))

    # --- build argv/env via the shared plan -----------------------------
    # The binary reads launch_conf_path (the temp copy under conf_geo="copy",
    # else the saved profile).
    chrome_args, env = build_launch_plan(
        chrome_path=chrome,
        profile_path=launch_conf_path,
        cdp_port=cdp_port,
        user_data_dir=user_data_dir,
        forwarder_port=forwarder_port,
        proxy_info=proxy_info,
        webrtc_spoof_ip=webrtc_spoof_ip,
        language=lang,
        timezone=tz,
        cdp_mode=cdp_mode_from_conf(launch_conf_path),
        headless=headless,
        extra_args=extra_args,
        url=url,
    )

    # --- launch ---------------------------------------------------------
    try:
        process = subprocess.Popen(chrome_args, env=env, **(popen_kwargs or {}))
    except Exception:
        # Roll back the forwarder/loop we started before the failure.
        if forwarder is not None and bgloop is not None:
            try:
                bgloop.run_coro(forwarder.stop(), timeout=3.0)
            except Exception:
                pass
        if bgloop is not None:
            bgloop.shutdown(timeout=3.0)
        if temp_conf is not None:
            try:
                temp_conf.unlink()
            except OSError:
                pass
        raise

    log.info(f"Chrome started (PID: {process.pid}, CDP: {cdp_port})")

    result = LaunchResult(
        process=process,
        cdp_port=cdp_port,
        profile_path=profile_path,
        user_data_dir=user_data_dir,
        forwarder=forwarder,
        bgloop=bgloop,
        webrtc_spoof_ip=webrtc_spoof_ip,
        geo=geo,
        temp_conf=temp_conf,
    )

    if wait_for_cdp:
        _wait_for_cdp(cdp_port, process, timeout=cdp_timeout)

    return result


class LaunchSession:
    """Thin context-manager wrapper around :func:`launch_persistent`.

    ``with LaunchSession(profile_path=...) as s: ...`` launches on enter and
    stops on exit. For fire-and-forget GUI use, call :func:`launch_persistent`
    directly and keep the returned :class:`LaunchResult`.
    """

    def __init__(self, **kwargs):
        self._kwargs = kwargs
        self.result: Optional[LaunchResult] = None

    def __enter__(self) -> LaunchResult:
        self.result = launch_persistent(**self._kwargs)
        return self.result

    def __exit__(self, *exc) -> None:
        if self.result is not None:
            self.result.stop()


def _wait_for_cdp(cdp_port: int, process: subprocess.Popen, timeout: float = 15.0) -> None:
    """Block until Chrome's CDP endpoint answers, or raise on timeout/exit."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/version")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                if data.get("webSocketDebuggerUrl"):
                    log.info("CDP ready")
                    return
        except Exception:
            pass
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited unexpectedly (code: {process.returncode})")
        time.sleep(0.3)
    raise TimeoutError(f"CDP not ready after {timeout}s on port {cdp_port}")
