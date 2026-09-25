"""NET-01: an ``https://`` upstream proxy must get TLS before credentials.

Before the fix both the forwarder (``_connect_http``) and the exit-IP probe
(``_detect_via_http_connect``) treated ``https`` exactly like ``http``: a plain
TCP socket carrying ``Proxy-Authorization: Basic <creds>`` in clear text.

Two layers of tests:

* a raw capture server (no crypto dependency) proves that for ``https`` the
  first bytes on the wire are a TLS record and that the Basic header never
  appears in clear, while ``http`` keeps sending the plain CONNECT unchanged;
* an end-to-end TLS proxy with a self-signed certificate (generated here with
  ``cryptography``; skipped if it is unavailable) proves the tunnel actually
  works through the forwarder and through ``detect_exit_ip``.
"""
import asyncio
import base64
import datetime
import ipaddress
import socket
import ssl
import struct
import threading

import pytest

from huligan import proxy
from huligan.proxy import ProxyForwarder

USER, PASSWORD = "alice", "s3cret"
BASIC = base64.b64encode(f"{USER}:{PASSWORD}".encode())


# ── raw capture server ───────────────────────────────────────────────────────

class _Capture:
    """Accepts one TCP connection, records the first bytes, answers nothing."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.data = b""
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        conn.settimeout(1.5)
        try:
            while len(self.data) < 4096:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                self.data += chunk
        except OSError:
            pass
        finally:
            conn.close()

    def join(self):
        self._t.join(timeout=5)
        self.sock.close()


def _probe(scheme, port):
    info = {"host": "127.0.0.1", "port": port, "user": USER,
            "password": PASSWORD, "type": scheme}
    return proxy.detect_exit_ip(info, timeout=1.0)


def test_https_probe_sends_tls_first_never_clear_creds():
    cap = _Capture()
    assert _probe("https", cap.port) is None  # capture server never answers
    cap.join()
    assert cap.data, "client sent nothing"
    assert cap.data[0] == 0x16, f"first byte is not a TLS handshake: {cap.data[:16]!r}"
    assert b"CONNECT" not in cap.data
    assert BASIC not in cap.data


def test_http_probe_unchanged_plain_connect():
    cap = _Capture()
    assert _probe("http", cap.port) is None
    cap.join()
    assert cap.data.startswith(b"CONNECT ifconfig.me:80 HTTP/1.1\r\n")
    assert b"Proxy-Authorization: Basic " + BASIC in cap.data


def _forwarder_connect(scheme, port):
    async def run():
        fwd = ProxyForwarder("127.0.0.1", port, USER, PASSWORD, upstream_type=scheme)
        try:
            await asyncio.wait_for(fwd._connect_http("example.com", 443), 3)
        except Exception:
            pass
        finally:
            await fwd.stop()
    asyncio.run(run())


def test_https_forwarder_sends_tls_first_never_clear_creds():
    cap = _Capture()
    _forwarder_connect("https", cap.port)
    cap.join()
    assert cap.data and cap.data[0] == 0x16, cap.data[:16]
    assert BASIC not in cap.data


def test_http_forwarder_unchanged_plain_connect():
    cap = _Capture()
    _forwarder_connect("http", cap.port)
    cap.join()
    assert cap.data.startswith(b"CONNECT example.com:443 HTTP/1.1\r\n")
    assert b"Proxy-Authorization: Basic " + BASIC in cap.data


# ── end-to-end TLS proxy with a self-signed certificate ─────────────────────

def _self_signed(tmp_path):
    crypto = pytest.importorskip(
        "cryptography", reason="cryptography not installed: cannot mint a test cert")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    del crypto

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "huligan-test-proxy")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName(
            [x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
             x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = tmp_path / "proxy.pem"
    key_pem = tmp_path / "proxy.key"
    cert_pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_pem.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    return str(cert_pem), str(key_pem)


class _TlsConnectProxy:
    """TLS-terminating CONNECT proxy; after 200 it plays the target itself.

    The "target" answers any HTTP request with the body ``203.0.113.7`` (the
    exit-IP probe) and otherwise echoes bytes back with an ``ECHO:`` prefix.
    """

    def __init__(self, cert, key):
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(cert, key)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.headers = []
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while True:
            try:
                raw, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(raw,), daemon=True).start()

    def _serve(self, raw):
        raw.settimeout(5)
        try:
            conn = self.ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            raw.close()
            return
        try:
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                head += chunk
            self.headers.append(head)
            if BASIC not in head:
                conn.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                return
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            data = conn.recv(4096)
            if data.startswith(b"GET "):
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\n"
                             b"Connection: close\r\n\r\n203.0.113.7")
            else:
                conn.sendall(b"ECHO:" + data)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.sock.close()


@pytest.fixture
def tls_proxy(tmp_path, monkeypatch):
    cert, key = _self_signed(tmp_path)
    srv = _TlsConnectProxy(cert, key)

    def trusting_ctx():
        ctx = ssl.create_default_context(cafile=cert)
        return ctx

    monkeypatch.setattr(proxy, "_proxy_ssl_context", trusting_ctx, raising=False)
    yield srv
    srv.close()


def test_https_probe_end_to_end_over_tls(tls_proxy):
    assert _probe("https", tls_proxy.port) == "203.0.113.7"
    assert tls_proxy.headers and b"Proxy-Authorization: Basic " + BASIC in tls_proxy.headers[0]


def test_https_probe_rejects_untrusted_cert(tls_proxy, monkeypatch):
    # Default (system) trust store does not know the self-signed cert:
    # verification must fail and no credentials may be delivered.
    monkeypatch.setattr(proxy, "_proxy_ssl_context", ssl.create_default_context,
                        raising=False)
    assert _probe("https", tls_proxy.port) is None
    assert tls_proxy.headers == []


def test_https_forwarder_end_to_end_over_tls(tls_proxy):
    async def run():
        fwd = ProxyForwarder("127.0.0.1", tls_proxy.port, USER, PASSWORD,
                             upstream_type="https")
        port = await fwd.start()
        try:
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(b"\x05\x01\x00")
            await w.drain()
            assert await r.readexactly(2) == b"\x05\x00"
            host = b"example.com"
            w.write(b"\x05\x01\x00\x03" + bytes([len(host)]) + host + struct.pack("!H", 443))
            await w.drain()
            reply = await asyncio.wait_for(r.readexactly(10), 5)
            assert reply[1] == 0, reply
            w.write(b"hello")
            await w.drain()
            assert await asyncio.wait_for(r.readexactly(10), 5) == b"ECHO:hello"
            w.close()
        finally:
            await fwd.stop()

    asyncio.run(run())
    assert b"CONNECT example.com:443" in tls_proxy.headers[0]
