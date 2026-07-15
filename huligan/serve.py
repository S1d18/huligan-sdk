"""``huligan serve`` - persistent CDP multiplexer.

One loopback HTTP port (default ``:9222``) fronts N patched-Chrome processes, one
per unique fingerprint seed. A client connects with::

    connect_over_cdp("http://localhost:9222/fp/<seed>")          # robust path form
    connect_over_cdp("http://localhost:9222?fingerprint=<seed>")  # query form

The multiplexer lazily spawns (or reuses) a :func:`launch_persistent` process for
that seed, rewrites the CDP ``webSocketDebuggerUrl`` back to itself, reverse-proxies
the DevTools WebSocket, and ref-counts + idle-GCs the processes.

Security (loopback-first):
  * binds ``127.0.0.1`` by default; a non-loopback ``host`` is refused without a token;
  * an Origin/Host guard rejects browser-originated (page) connections, mirroring the
    binary's ``05_cdp_stealth`` rule - the real CDP ports run ``--remote-allow-origins=*``
    with Chrome's own check disabled, so this mux is the only line of defense.

Zero new dependencies: pure ``asyncio``. The WebSocket leg is a transparent TCP splice
after the ``101`` handshake (both legs are plaintext loopback ``ws://``), reusing the
bidirectional-relay pattern from :class:`huligan.proxy.ProxyForwarder`.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .fingerprint import FingerprintProfile
from .persistent import launch_persistent

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9222
DEFAULT_IDLE_TIMEOUT = 300.0
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "[::1]", "::1", "")


@dataclass
class ServeConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    cdp_mode: str = "isolated"          # served procs default to isolated so Runtime.evaluate works
    proxy: Optional[str] = None
    token: Optional[str] = None
    serve_root: Optional[Path] = None
    headless: bool = True
    geoip: bool = True
    allow_origins: Tuple[str, ...] = ()
    max_processes: int = 0              # 0 = unlimited


@dataclass
class _SeedProcess:
    result: object                      # persistent.LaunchResult
    real_cdp_port: int
    ref_count: int = 0
    last_active: float = 0.0
    gc_handle: Optional[asyncio.TimerHandle] = None


class _MaxProcessesError(RuntimeError):
    pass


# --- request/response plumbing (stdlib only) ------------------------------

async def _read_http_head(reader: asyncio.StreamReader):
    """Return ``(method, target, headers_lower, raw_header_lines)`` or ``None``."""
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError,
            asyncio.TimeoutError, ConnectionError):
        return None
    lines = head.decode("latin-1", "replace").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None
    method, target = parts[0], parts[1]
    raw_lines = [ln for ln in lines[1:] if ln]
    headers = {}
    for ln in raw_lines:
        if ":" in ln:
            k, v = ln.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return method, target, headers, raw_lines


async def _send_simple(writer: asyncio.StreamWriter, code: int, msg: str) -> None:
    body = msg.encode()
    resp = (
        f"HTTP/1.1 {code} {msg}\r\n"
        f"Content-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body
    try:
        writer.write(resp)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _send_json(writer: asyncio.StreamWriter, body: bytes) -> None:
    resp = (
        f"HTTP/1.1 200 OK\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body
    try:
        writer.write(resp)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


def _fetch_version(real_port: int) -> Optional[dict]:
    """Blocking GET of a backend Chrome's /json/version (run in an executor).

    No Origin header is sent, so the binary's 05_cdp_stealth guard allows it.
    """
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{real_port}/json/version", timeout=5
        ) as r:
            return json.load(r)
    except Exception:
        return None


async def _relay(client_r, client_w, up_r, up_w) -> None:
    """Bidirectional byte splice (the ProxyForwarder._relay pattern)."""
    async def pipe(src, dst):
        try:
            while True:
                data = await src.read(65536)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            try:
                dst.close()
            except Exception:
                pass

    t1 = asyncio.create_task(pipe(client_r, up_w))
    t2 = asyncio.create_task(pipe(up_r, client_w))
    try:
        await asyncio.gather(t1, t2)
    except asyncio.CancelledError:
        t1.cancel()
        t2.cancel()


# --- pure helpers (unit-tested) -------------------------------------------

def _origin_allowed(headers: dict, allow_origins) -> bool:
    """05_cdp_stealth rule: a missing Origin is allowed (automation clients send
    none); loopback/allowlisted Origins are allowed; a page Origin is rejected."""
    origin = headers.get("origin")
    if not origin:
        return True
    o = origin.lower()
    if (o.startswith("http://localhost") or o.startswith("http://127.0.0.1")
            or o.startswith("https://localhost") or o.startswith("https://127.0.0.1")):
        return True
    return origin in tuple(allow_origins)


def _host_is_loopback(headers: dict) -> bool:
    host = headers.get("host", "")
    hostname = host.rsplit(":", 1)[0] if ":" in host else host
    return hostname in _LOOPBACK_HOSTS


def _token_ok(auth_header: str, token: str) -> bool:
    prefix = "bearer "
    if auth_header.lower().startswith(prefix):
        return hmac.compare_digest(auth_header[len(prefix):].strip(), token)
    return False


def _extract_seed(target: str) -> Optional[str]:
    """Pull the fingerprint seed from an HTTP request-target, tolerating
    Playwright's string-concat of ``/json/version`` onto the endpoint URL
    (``http://host:port?fingerprint=42`` -> target ``/?fingerprint=42/json/version``)."""
    t = target
    for suffix in ("/json/version", "/json/list", "/json/new", "/json"):
        if t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    if "/fp/" in t:
        return (t.split("/fp/", 1)[1].strip("/").split("/")[0]) or None
    if "fingerprint=" in t:
        return (t.split("fingerprint=", 1)[1].split("&")[0].strip("/")) or None
    return None


def _parse_ws_target(target: str) -> Tuple[Optional[str], Optional[str]]:
    """``/seed/<seed>/devtools/browser/<guid>`` -> ``(seed, /devtools/browser/<guid>)``."""
    if not target.startswith("/seed/"):
        return None, None
    seed, sep, real = target[len("/seed/"):].partition("/")
    if not sep:
        return (seed or None), None
    return (seed or None), "/" + real


def _rebuild_upgrade_request(real_path: str, raw_lines: List[str], real_port: int) -> bytes:
    """Reconstruct the client's WebSocket upgrade for the backend, rewriting only
    the request path and Host so the client's Sec-WebSocket-Key survives intact."""
    out = [f"GET {real_path} HTTP/1.1"]
    for ln in raw_lines:
        if ln.lower().startswith("host:"):
            out.append(f"Host: 127.0.0.1:{real_port}")
        else:
            out.append(ln)
    return ("\r\n".join(out) + "\r\n\r\n").encode("latin-1", "replace")


# --- the multiplexer ------------------------------------------------------

class ServeMux:
    def __init__(self, config: ServeConfig):
        self.cfg = config
        self.registry: Dict[str, _SeedProcess] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._server: Optional[asyncio.AbstractServer] = None
        self._reaper: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.serve_root = (Path(config.serve_root) if config.serve_root
                           else Path.home() / ".huligan" / "serve")

    def _lock_for(self, seed_key: str) -> asyncio.Lock:
        lk = self._locks.get(seed_key)
        if lk is None:
            lk = asyncio.Lock()
            self._locks[seed_key] = lk
        return lk

    async def start(self) -> "ServeMux":
        self._loop = asyncio.get_event_loop()
        if self.cfg.host not in _LOOPBACK_HOSTS and not self.cfg.token:
            raise RuntimeError(
                f"Refusing to bind non-loopback host {self.cfg.host!r} without a token. "
                "Set token=/--token (or HULIGAN_SERVE_TOKEN), or bind 127.0.0.1."
            )
        self._server = await asyncio.start_server(self._on_conn, self.cfg.host, self.cfg.port)
        self._reaper = asyncio.ensure_future(self._reap_loop())
        return self

    async def stop(self) -> None:
        if self._reaper:
            self._reaper.cancel()
            self._reaper = None
        if self._server:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        for entry in list(self.registry.values()):
            try:
                await self._loop.run_in_executor(None, entry.result.stop)
            except Exception:
                pass
        self.registry.clear()

    async def serve_forever(self) -> None:
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    # -- connection dispatch --

    async def _on_conn(self, reader, writer):
        try:
            head = await _read_http_head(reader)
            if head is None:
                writer.close()
                return
            _method, target, headers, raw_lines = head

            if self.cfg.token and not _token_ok(headers.get("authorization", ""), self.cfg.token):
                await _send_simple(writer, 403, "forbidden")
                return
            if not (_origin_allowed(headers, self.cfg.allow_origins) and _host_is_loopback(headers)):
                await _send_simple(writer, 404, "not found")
                return

            if headers.get("upgrade", "").lower() == "websocket" and target.startswith("/seed/"):
                await self._handle_ws(reader, writer, target, raw_lines)
            elif target.endswith(("/json/version", "/json", "/json/list", "/json/new")):
                await self._handle_version(writer, target)
            else:
                await _send_simple(writer, 404, "not found")
        except Exception:
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_version(self, writer, target):
        seed = _extract_seed(target)
        if seed is None:
            await _send_simple(writer, 400, "missing fingerprint seed")
            return
        try:
            int(seed)
        except ValueError:
            await _send_simple(writer, 400, "fingerprint seed must be an integer")
            return
        try:
            entry = await self._acquire(seed)
        except _MaxProcessesError:
            await _send_simple(writer, 503, "max processes reached")
            return
        except Exception as e:
            await _send_simple(writer, 502, f"spawn failed: {e}")
            return

        real = await self._loop.run_in_executor(None, _fetch_version, entry.real_cdp_port)
        if not real or "webSocketDebuggerUrl" not in real:
            await _send_simple(writer, 502, "backend cdp unavailable")
            return
        real_path = urllib.parse.urlparse(real["webSocketDebuggerUrl"]).path
        out = dict(real)
        out["webSocketDebuggerUrl"] = f"ws://{self.cfg.host}:{self.cfg.port}/seed/{int(seed)}{real_path}"
        await _send_json(writer, json.dumps(out).encode())

    async def _handle_ws(self, client_r, client_w, target, raw_lines):
        seed, real_path = _parse_ws_target(target)
        if seed is None or real_path is None:
            await _send_simple(client_w, 404, "bad seed path")
            return
        try:
            seed_key = str(int(seed))
        except ValueError:
            await _send_simple(client_w, 400, "bad seed")
            return

        entry = self.registry.get(seed_key)
        if entry is None or entry.result.poll() is not None:
            try:
                entry = await self._acquire(seed_key)   # reconnect after GC / restart
            except Exception:
                await _send_simple(client_w, 502, "no process for seed")
                return

        try:
            up_r, up_w = await asyncio.open_connection("127.0.0.1", entry.real_cdp_port)
        except Exception:
            await _send_simple(client_w, 502, "backend connect failed")
            return

        try:
            up_w.write(_rebuild_upgrade_request(real_path, raw_lines, entry.real_cdp_port))
            await up_w.drain()
        except Exception:
            await _send_simple(client_w, 502, "backend upgrade failed")
            try:
                up_w.close()
            except Exception:
                pass
            return

        self._ref_inc(entry)
        try:
            await _relay(client_r, client_w, up_r, up_w)
        finally:
            self._ref_dec(entry)
            for w in (up_w, client_w):
                try:
                    w.close()
                except Exception:
                    pass

    # -- spawn / reuse (first-launch-wins) --

    async def _acquire(self, seed) -> _SeedProcess:
        seed_key = str(int(seed))
        entry = self.registry.get(seed_key)
        if entry and entry.result.poll() is None:
            return entry
        async with self._lock_for(seed_key):
            entry = self.registry.get(seed_key)
            if entry and entry.result.poll() is None:
                return entry
            if self.cfg.max_processes and len(self.registry) >= self.cfg.max_processes:
                raise _MaxProcessesError()
            result = await self._loop.run_in_executor(None, self._spawn, seed_key)
            entry = _SeedProcess(result=result, real_cdp_port=result.cdp_port,
                                 last_active=self._loop.time())
            self.registry[seed_key] = entry
            return entry

    def _spawn(self, seed_key: str):
        """Synchronous spawn (runs in an executor so it never blocks the loop)."""
        profile = FingerprintProfile.from_seed(int(seed_key))
        if self.cfg.cdp_mode in ("paranoid", "isolated"):
            profile.cdp_mode = self.cfg.cdp_mode
        seed_dir = self.serve_root / seed_key
        seed_dir.mkdir(parents=True, exist_ok=True)
        conf_path = seed_dir / "profile.conf"
        conf_path.write_text(profile.to_conf(), encoding="utf-8")
        udd = seed_dir / "user-data"
        udd.mkdir(exist_ok=True)
        return launch_persistent(
            profile_path=conf_path,
            user_data_dir=udd,
            proxy=self.cfg.proxy,
            headless=self.cfg.headless,
            geoip=self.cfg.geoip,
            wait_for_cdp=True,
        )

    # -- lifecycle --

    def _ref_inc(self, entry: _SeedProcess) -> None:
        entry.ref_count += 1
        if entry.gc_handle is not None:
            entry.gc_handle.cancel()          # cancel-cleanup on reconnect within idle window
            entry.gc_handle = None

    def _ref_dec(self, entry: _SeedProcess) -> None:
        entry.ref_count -= 1
        entry.last_active = self._loop.time()
        if entry.ref_count <= 0:
            entry.gc_handle = self._loop.call_later(self.cfg.idle_timeout, self._gc, entry)

    def _gc(self, entry: _SeedProcess) -> None:
        if entry.ref_count > 0:
            return
        key = next((k for k, v in self.registry.items() if v is entry), None)
        if key is not None:
            self.registry.pop(key, None)
        self._loop.run_in_executor(None, entry.result.stop)

    async def _reap_loop(self) -> None:
        """Drop registry entries whose Chrome self-exited."""
        try:
            while True:
                await asyncio.sleep(30)
                for key, entry in list(self.registry.items()):
                    if entry.result.poll() is not None:
                        self.registry.pop(key, None)
        except asyncio.CancelledError:
            pass


def serve(**kwargs) -> None:
    """Blocking entry point used by ``huligan serve`` (and importable directly)."""
    cfg = ServeConfig(**kwargs)

    async def _main():
        mux = ServeMux(cfg)
        await mux.start()
        print(
            f"huligan serve on http://{cfg.host}:{cfg.port}  "
            f"(connect_over_cdp .../fp/<seed>  |  cdp_mode={cfg.cdp_mode})"
        )
        try:
            await mux.serve_forever()
        finally:
            await mux.stop()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


run_serve = serve  # alias mirroring huligan.mcp.run
