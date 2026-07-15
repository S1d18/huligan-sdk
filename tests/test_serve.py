"""Tests for the huligan serve CDP multiplexer (T1.1): pure helpers + lifecycle.

The lifecycle tests drive a fake process (no Chrome), so they are fast and CI-safe.
End-to-end two-identity isolation is verified live against a real binary separately.
"""
import asyncio

import pytest

from huligan import serve as srv
from huligan.serve import ServeConfig, ServeMux


# --- pure helpers ---------------------------------------------------------

def test_extract_seed_path_form():
    assert srv._extract_seed("/fp/42/json/version") == "42"
    assert srv._extract_seed("/fp/8675309/json") == "8675309"


def test_extract_seed_query_form_playwright_concat():
    # Playwright concatenates "/json/version" onto "http://h:p?fingerprint=42".
    assert srv._extract_seed("/?fingerprint=42/json/version") == "42"
    assert srv._extract_seed("/?fingerprint=7&x=1/json/version") == "7"


def test_extract_seed_none():
    assert srv._extract_seed("/json/version") is None
    assert srv._extract_seed("/random") is None


def test_parse_ws_target():
    seed, path = srv._parse_ws_target("/seed/42/devtools/browser/abc-123")
    assert seed == "42" and path == "/devtools/browser/abc-123"
    assert srv._parse_ws_target("/nope") == (None, None)


def test_origin_guard():
    assert srv._origin_allowed({}, ()) is True                        # no Origin -> allow
    assert srv._origin_allowed({"origin": "http://127.0.0.1:9222"}, ()) is True
    assert srv._origin_allowed({"origin": "https://evil.example"}, ()) is False
    assert srv._origin_allowed({"origin": "https://evil.example"}, ("https://evil.example",)) is True


def test_host_guard():
    assert srv._host_is_loopback({"host": "127.0.0.1:9222"}) is True
    assert srv._host_is_loopback({"host": "localhost:9222"}) is True
    assert srv._host_is_loopback({"host": "evil.example:9222"}) is False


def test_token_guard():
    assert srv._token_ok("Bearer s3cret", "s3cret") is True
    assert srv._token_ok("Bearer wrong", "s3cret") is False
    assert srv._token_ok("", "s3cret") is False


def test_rebuild_upgrade_request_keeps_key_rewrites_host_and_path():
    raw = ["Host: 127.0.0.1:9222", "Upgrade: websocket", "Connection: Upgrade",
           "Sec-WebSocket-Key: dGhlIHNhbXBsZQ==", "Sec-WebSocket-Version: 13"]
    out = srv._rebuild_upgrade_request("/devtools/browser/xyz", raw, 55123).decode()
    assert out.startswith("GET /devtools/browser/xyz HTTP/1.1\r\n")
    assert "Host: 127.0.0.1:55123" in out
    assert "Sec-WebSocket-Key: dGhlIHNhbXBsZQ==" in out               # key survives -> Accept matches
    assert out.endswith("\r\n\r\n")


# --- lifecycle (fake process, no Chrome) ----------------------------------

class _FakeResult:
    def __init__(self, port=55123):
        self._alive = True
        self.cdp_port = port
        self.stopped = False

    def poll(self):
        return None if self._alive else 0

    def stop(self):
        self.stopped = True
        self._alive = False


def _mux_with_fake(monkeypatch, **cfg):
    mux = ServeMux(ServeConfig(**cfg))
    spawned = []

    def _fake_spawn(seed_key):
        r = _FakeResult(port=55000 + int(seed_key))
        spawned.append((seed_key, r))
        return r

    monkeypatch.setattr(mux, "_spawn", _fake_spawn)
    return mux, spawned


def test_first_launch_wins(monkeypatch):
    async def run():
        mux, spawned = _mux_with_fake(monkeypatch)
        mux._loop = asyncio.get_event_loop()
        e1 = await mux._acquire("42")
        e2 = await mux._acquire("42")            # same seed -> same process reused
        assert e1 is e2
        assert len(spawned) == 1 and len(mux.registry) == 1
    asyncio.run(run())


def test_two_seeds_two_processes(monkeypatch):
    async def run():
        mux, _ = _mux_with_fake(monkeypatch)
        mux._loop = asyncio.get_event_loop()
        a = await mux._acquire("1")
        b = await mux._acquire("2")
        assert a is not b and len(mux.registry) == 2
        assert a.real_cdp_port != b.real_cdp_port
    asyncio.run(run())


def test_idle_gc_and_cancel_cleanup(monkeypatch):
    async def run():
        mux, _ = _mux_with_fake(monkeypatch, idle_timeout=0.05)
        mux._loop = asyncio.get_event_loop()
        entry = await mux._acquire("42")
        mux._ref_inc(entry)
        mux._ref_dec(entry)                      # ref 0 -> schedules GC
        assert entry.gc_handle is not None
        mux._ref_inc(entry)                      # reconnect within window cancels GC
        assert entry.gc_handle is None
        mux._ref_dec(entry)                      # schedule again
        await asyncio.sleep(0.2)                 # let it fire
        assert entry.result.stopped is True
        assert "42" not in mux.registry
    asyncio.run(run())


def test_max_processes(monkeypatch):
    async def run():
        mux, _ = _mux_with_fake(monkeypatch, max_processes=1)
        mux._loop = asyncio.get_event_loop()
        await mux._acquire("1")
        with pytest.raises(srv._MaxProcessesError):
            await mux._acquire("2")
    asyncio.run(run())


def test_nonloopback_without_token_refused():
    async def run():
        mux = ServeMux(ServeConfig(host="0.0.0.0"))
        with pytest.raises(RuntimeError):
            await mux.start()
    asyncio.run(run())
