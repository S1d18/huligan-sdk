"""SOCKS5 UDP ASSOCIATE relay in ProxyForwarder, both branches.

Real proxies mostly refuse UDP (the one this was developed against answers
0x07 command-not-supported), so the working path can only be exercised against a
mock upstream. Without this test the relay would ship unverified — the exact
pattern that left five dead spoofs in the 151 build.
"""
import asyncio
import socket
import struct

import pytest

from huligan.proxy import ProxyForwarder


class _UdpEcho(asyncio.DatagramProtocol):
    """Destination service: echoes the payload back with a marker."""

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.transport.sendto(b"ECHO:" + data, addr)


class _MockSocks5:
    """Minimal SOCKS5 upstream; ``udp_ok`` toggles UDP ASSOCIATE support."""

    def __init__(self, udp_ok=True):
        self.udp_ok = udp_ok
        self.server = None
        self.relay_transport = None

    async def start(self):
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def close(self):
        if self.server:
            self.server.close()
        if self.relay_transport:
            self.relay_transport.close()

    async def _client(self, reader, writer):
        try:
            head = await reader.readexactly(2)
            await reader.readexactly(head[1])
            writer.write(b"\x05\x00")
            await writer.drain()

            req = await reader.readexactly(4)
            cmd, atyp = req[1], req[3]
            if atyp == 0x01:
                await reader.readexactly(4)
            elif atyp == 0x03:
                await reader.readexactly((await reader.readexactly(1))[0])
            await reader.readexactly(2)

            if cmd == 0x03 and self.udp_ok:
                await self._serve_udp(reader, writer)
            else:
                writer.write(struct.pack("!BBBBIH", 5, 7, 0, 1, 0, 0))
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _serve_udp(self, reader, writer):
        loop = asyncio.get_running_loop()
        outer = self

        class Relay(asyncio.DatagramProtocol):
            """Decapsulate, forward, re-encapsulate — fully async.

            A blocking recvfrom here would sit on the same event loop as the
            forwarder and the echo destination and deadlock all three.
            """

            def connection_made(self, transport):
                self.transport = transport

            def datagram_received(self, data, addr):
                if data[:3] == b"\x00\x00\x00" and data[3] == 0x01:
                    dst = socket.inet_ntoa(data[4:8])
                    dport = struct.unpack("!H", data[8:10])[0]
                    asyncio.ensure_future(
                        self._fwd(data[10:], dst, dport, data[4:10], addr))

            async def _fwd(self, payload, dst, dport, hdr, back_to):
                fut = loop.create_future()

                class One(asyncio.DatagramProtocol):
                    def connection_made(self, tr):
                        tr.sendto(payload, (dst, dport))

                    def datagram_received(self, d, _a):
                        if not fut.done():
                            fut.set_result(d)

                tr, _ = await loop.create_datagram_endpoint(
                    One, local_addr=("127.0.0.1", 0))
                try:
                    back = await asyncio.wait_for(fut, timeout=5)
                    self.transport.sendto(b"\x00\x00\x00\x01" + hdr + back, back_to)
                except Exception:
                    pass
                finally:
                    tr.close()

        outer.relay_transport, _ = await loop.create_datagram_endpoint(
            Relay, local_addr=("127.0.0.1", 0))
        host, port = outer.relay_transport.get_extra_info("sockname")[:2]
        writer.write(b"\x05\x00\x00\x01" + socket.inet_aton(host)
                     + struct.pack("!H", port))
        await writer.drain()
        await reader.read()


def _client_associate(local_port, echo_port=None):
    """Speak SOCKS5 to the forwarder as Chrome would. Runs off the event loop."""
    c = socket.create_connection(("127.0.0.1", local_port), timeout=10)
    try:
        c.sendall(b"\x05\x01\x00")
        c.recv(2)
        c.sendall(b"\x05\x03\x00\x01" + socket.inet_aton("0.0.0.0")
                  + struct.pack("!H", 0))
        head = c.recv(4)
        if head[1] != 0x00 or echo_port is None:
            return head[1], None
        addr = socket.inet_ntoa(c.recv(4))
        port = struct.unpack("!H", c.recv(2))[0]
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.settimeout(8)
        try:
            u.sendto(b"\x00\x00\x00\x01" + socket.inet_aton("127.0.0.1")
                     + struct.pack("!H", echo_port) + b"hello-udp", (addr, port))
            data, _ = u.recvfrom(2048)
            return head[1], data[10:]
        finally:
            u.close()
    finally:
        c.close()


async def _run(udp_ok):
    loop = asyncio.get_running_loop()
    echo_t, _ = await loop.create_datagram_endpoint(
        _UdpEcho, local_addr=("127.0.0.1", 0))
    echo_port = echo_t.get_extra_info("sockname")[1]

    up = _MockSocks5(udp_ok=udp_ok)
    up_port = await up.start()
    fwd = ProxyForwarder("127.0.0.1", up_port, "", "", upstream_type="socks5")
    local_port = await fwd.start()
    try:
        rep, payload = await loop.run_in_executor(
            None, _client_associate, local_port, echo_port if udp_ok else None)
        return fwd.udp_supported, rep, payload
    finally:
        await fwd.stop()
        await up.close()
        echo_t.close()
        await asyncio.sleep(0.1)


def test_udp_relay_round_trip_when_upstream_supports_it():
    supported, rep, payload = asyncio.run(_run(True))
    assert supported is True
    assert rep == 0x00
    assert payload == b"ECHO:hello-udp"


def test_degrades_cleanly_when_upstream_refuses_udp():
    """A TCP-only upstream must not break anything — Chrome just gets 0x07."""
    supported, rep, _ = asyncio.run(_run(False))
    assert supported is False
    assert rep == 0x07


def test_http_upstream_never_advertises_udp():
    """HTTP CONNECT proxies have no UDP concept; don't even probe them."""

    async def go():
        fwd = ProxyForwarder("127.0.0.1", 1, "", "", upstream_type="http")
        await fwd.start()
        try:
            return fwd.udp_supported
        finally:
            await fwd.stop()

    assert asyncio.run(go()) is False
