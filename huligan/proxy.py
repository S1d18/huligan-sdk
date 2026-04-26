"""
Huligan Antidetect - Proxy Forwarder

Local SOCKS5 proxy that bridges Chrome (no-auth) to upstream proxy (with auth).

Chrome does not support SOCKS5 authentication natively. This forwarder listens
on 127.0.0.1 without auth and forwards traffic to an upstream proxy with
credentials.

Supported upstream types:
  - SOCKS5 with username/password auth
  - HTTP CONNECT with Basic auth

Usage:
    from huligan.proxy import ProxyForwarder, parse_proxy_string

    info = parse_proxy_string("socks5://user:pass@host:port")
    forwarder = ProxyForwarder(info["host"], info["port"], info["user"], info["password"])
    local_port = await forwarder.start()
    # Chrome connects to socks5://127.0.0.1:<local_port>
    await forwarder.stop()
"""

import asyncio
import base64
import logging
import socket
import struct
from typing import Optional

log = logging.getLogger("huligan.proxy")


class ProxyForwarder:
    """
    Local SOCKS5 server (no auth) that forwards to an upstream proxy (with auth).
    """

    def __init__(
        self,
        upstream_host: str,
        upstream_port: int,
        upstream_user: str,
        upstream_pass: str,
        upstream_type: str = "socks5",
        local_host: str = "127.0.0.1",
        local_port: int = 0,  # 0 = random available port
    ):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.upstream_user = upstream_user
        self.upstream_pass = upstream_pass
        self.upstream_type = upstream_type.lower()
        self.local_host = local_host
        self.local_port = local_port
        self._server: Optional[asyncio.AbstractServer] = None
        self._active_tasks: set = set()

    @property
    def port(self) -> int:
        """The actual local port (resolved after start if was 0)."""
        if self._server and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self.local_port

    async def start(self) -> int:
        """Start the local SOCKS5 server. Returns the local port."""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.local_host,
            self.local_port,
        )
        actual_port = self.port
        log.info(f"Forwarder listening on {self.local_host}:{actual_port}")
        log.info(f"Upstream: {self.upstream_type}://{self.upstream_host}:{self.upstream_port}")
        return actual_port

    async def stop(self):
        """Stop the server and all active connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        # Cancel active tasks
        for task in self._active_tasks:
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)
        self._active_tasks.clear()
        log.info("Forwarder stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming SOCKS5 connection from Chrome."""
        task = asyncio.current_task()
        self._active_tasks.add(task)
        peer = writer.get_extra_info("peername")
        try:
            # SOCKS5 handshake (RFC 1928)
            header = await reader.readexactly(2)
            version, nmethods = struct.unpack("!BB", header)
            if version != 5:
                log.warning(f"[{peer}] Not SOCKS5 (version={version})")
                writer.close()
                return
            methods = await reader.readexactly(nmethods)

            # Reply: no auth required (0x00)
            writer.write(struct.pack("!BB", 5, 0))
            await writer.drain()

            # Client request
            header = await reader.readexactly(4)
            ver, cmd, rsv, atyp = struct.unpack("!BBBB", header)

            if cmd != 1:  # Only CONNECT supported
                writer.write(struct.pack("!BBBBIH", 5, 7, 0, 1, 0, 0))
                await writer.drain()
                writer.close()
                return

            # Parse target address
            if atyp == 1:  # IPv4
                raw_addr = await reader.readexactly(4)
                target_host = socket.inet_ntoa(raw_addr)
            elif atyp == 3:  # Domain
                domain_len = (await reader.readexactly(1))[0]
                target_host = (await reader.readexactly(domain_len)).decode()
            elif atyp == 4:  # IPv6
                raw_addr = await reader.readexactly(16)
                target_host = socket.inet_ntop(socket.AF_INET6, raw_addr)
            else:
                writer.write(struct.pack("!BBBBIH", 5, 8, 0, 1, 0, 0))
                await writer.drain()
                writer.close()
                return

            raw_port = await reader.readexactly(2)
            target_port = struct.unpack("!H", raw_port)[0]

            log.debug(f"[{peer}] CONNECT {target_host}:{target_port}")

            # Connect through upstream proxy
            try:
                if self.upstream_type == "socks5":
                    upstream_r, upstream_w = await self._connect_socks5(target_host, target_port)
                elif self.upstream_type in ("http", "https"):
                    upstream_r, upstream_w = await self._connect_http(target_host, target_port)
                else:
                    raise ValueError(f"Unknown upstream type: {self.upstream_type}")
            except Exception as e:
                log.error(f"[{peer}] Upstream connect failed: {e}")
                writer.write(struct.pack("!BBBBIH", 5, 1, 0, 1, 0, 0))
                await writer.drain()
                writer.close()
                return

            # Reply: success
            writer.write(struct.pack("!BBBBIH", 5, 0, 0, 1, 0, 0))
            await writer.drain()

            # Relay data bidirectionally
            await self._relay(reader, writer, upstream_r, upstream_w)

        except (asyncio.IncompleteReadError, ConnectionError, OSError) as e:
            log.debug(f"[{peer}] Connection closed: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[{peer}] Error: {e}")
        finally:
            writer.close()
            self._active_tasks.discard(task)

    async def _connect_socks5(self, target_host: str, target_port: int):
        """Connect to target through upstream SOCKS5 proxy with auth."""
        reader, writer = await asyncio.open_connection(
            self.upstream_host, self.upstream_port
        )
        try:
            # Greeting: offer username/password auth (method 0x02)
            writer.write(struct.pack("!BBB", 5, 1, 2))
            await writer.drain()

            resp = await reader.readexactly(2)
            ver, method = struct.unpack("!BB", resp)
            if method != 2:
                raise ConnectionError(f"SOCKS5 upstream rejected auth (method={method})")

            # Username/password auth (RFC 1929)
            user_bytes = self.upstream_user.encode()
            pass_bytes = self.upstream_pass.encode()
            auth_msg = struct.pack("!BB", 1, len(user_bytes)) + user_bytes
            auth_msg += struct.pack("!B", len(pass_bytes)) + pass_bytes
            writer.write(auth_msg)
            await writer.drain()

            resp = await reader.readexactly(2)
            auth_ver, status = struct.unpack("!BB", resp)
            if status != 0:
                raise ConnectionError(f"SOCKS5 auth failed (status={status})")

            # CONNECT request
            connect_msg = struct.pack("!BBBB", 5, 1, 0, 3)  # domain type
            host_bytes = target_host.encode()
            connect_msg += struct.pack("!B", len(host_bytes)) + host_bytes
            connect_msg += struct.pack("!H", target_port)
            writer.write(connect_msg)
            await writer.drain()

            # Parse reply
            resp = await reader.readexactly(4)
            ver, rep, rsv, atyp = struct.unpack("!BBBB", resp)
            if rep != 0:
                raise ConnectionError(f"SOCKS5 CONNECT failed (rep={rep})")

            # Skip bound address
            if atyp == 1:
                await reader.readexactly(4 + 2)
            elif atyp == 3:
                domain_len = (await reader.readexactly(1))[0]
                await reader.readexactly(domain_len + 2)
            elif atyp == 4:
                await reader.readexactly(16 + 2)

            return reader, writer

        except Exception:
            writer.close()
            raise

    async def _connect_http(self, target_host: str, target_port: int):
        """Connect to target through upstream HTTP CONNECT proxy with auth."""
        reader, writer = await asyncio.open_connection(
            self.upstream_host, self.upstream_port
        )
        try:
            creds = base64.b64encode(
                f"{self.upstream_user}:{self.upstream_pass}".encode()
            ).decode()
            connect_req = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n"
                f"Proxy-Authorization: Basic {creds}\r\n"
                f"Proxy-Connection: keep-alive\r\n"
                f"\r\n"
            )
            writer.write(connect_req.encode())
            await writer.drain()

            response_line = await reader.readline()
            if not response_line:
                raise ConnectionError("Empty response from HTTP proxy")

            status_line = response_line.decode(errors="replace").strip()
            parts = status_line.split(" ", 2)
            if len(parts) < 2:
                raise ConnectionError(f"Invalid HTTP proxy response: {status_line}")

            status_code = int(parts[1])
            if status_code != 200:
                raise ConnectionError(f"HTTP CONNECT failed: {status_line}")

            # Read and discard remaining headers
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            return reader, writer

        except Exception:
            writer.close()
            raise

    async def _relay(
        self,
        client_r: asyncio.StreamReader,
        client_w: asyncio.StreamWriter,
        upstream_r: asyncio.StreamReader,
        upstream_w: asyncio.StreamWriter,
    ):
        """Bidirectional data relay between client and upstream."""

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter):
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

        t1 = asyncio.create_task(pipe(client_r, upstream_w))
        t2 = asyncio.create_task(pipe(upstream_r, client_w))
        try:
            await asyncio.gather(t1, t2)
        except asyncio.CancelledError:
            t1.cancel()
            t2.cancel()


def parse_proxy_string(proxy_str: str) -> dict:
    """
    Parse proxy string in various formats.

    Supported formats:
        IP:PORT:USER:PASS
        USER:PASS@IP:PORT
        socks5://USER:PASS@IP:PORT
        http://IP:PORT:USER:PASS
        IP:PORT (no auth)

    Returns:
        dict with keys: host, port, user, password, type

    Note:
        If the proxy string does not include an explicit protocol prefix
        (e.g. ``socks5://`` or ``http://``), the type defaults to ``"socks5"``.
        This is legacy CLI behavior. The GUI profile model
        (``gui/models/profile.py``) defaults to ``"http"`` — callers should
        pass the protocol explicitly when the source is a GUI profile.
    """
    proxy_str = proxy_str.strip()
    proxy_type = "socks5"  # default for CLI / legacy callers (see docstring)

    # Extract protocol
    if "://" in proxy_str:
        proto, proxy_str = proxy_str.split("://", 1)
        proxy_type = proto.lower()

    # Format: USER:PASS@IP:PORT
    if "@" in proxy_str:
        auth, host_port = proxy_str.rsplit("@", 1)
        parts = host_port.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 1080
        auth_parts = auth.split(":", 1)
        user = auth_parts[0]
        password = auth_parts[1] if len(auth_parts) > 1 else ""
    else:
        # Format: IP:PORT:USER:PASS
        parts = proxy_str.split(":")
        if len(parts) == 4:
            host, port, user, password = parts[0], int(parts[1]), parts[2], parts[3]
        elif len(parts) == 2:
            host, port = parts[0], int(parts[1])
            user, password = "", ""
        else:
            raise ValueError(f"Cannot parse proxy string: {proxy_str}")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "type": proxy_type,
    }
