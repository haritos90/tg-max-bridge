import socket
import threading

import pytest

from tg_max_bridge import http as h


def test_ipv4_sorted_first(monkeypatch):
    infos = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 443, 0, 0)),
             (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    infos.sort(key=lambda i: i[0] != socket.AF_INET)
    assert infos[0][0] == socket.AF_INET


def test_connect_fails_over_to_next_address(monkeypatch):
    # A listening socket stands in for the reachable address.
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted = []
    threading.Thread(target=lambda: accepted.append(srv.accept()[0]), daemon=True).start()
    monkeypatch.setattr(h, "CONNECT_TIMEOUT", 0.3)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.255.255.1", 9)),  # black hole
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))])
    conn = h._Connection("example.invalid", port, timeout=5)
    monkeypatch.setattr(conn._context, "wrap_socket", lambda s, server_hostname: s)
    conn.connect()
    assert conn.sock.getpeername()[1] == port
    assert conn.sock.gettimeout() == 5
    conn.close()
    srv.close()


def test_connect_raises_when_no_address_works(monkeypatch):
    monkeypatch.setattr(h, "CONNECT_TIMEOUT", 0.2)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.255.255.1", 9))])
    conn = h._Connection("example.invalid", 9, timeout=5)
    with pytest.raises(OSError):
        conn.connect()
