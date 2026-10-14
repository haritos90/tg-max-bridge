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


def test_multipart_body_shape(monkeypatch):
    client = h.JsonClient("https://example.invalid")
    captured = {}

    def fake_raw(method, url, data, headers, timeout):
        captured.update(method=method, url=url, data=data, headers=headers)
        return b'{"ok":true}', "application/json"

    monkeypatch.setattr(client, "_raw", fake_raw)
    out = client.post_multipart("/sendPhoto", {"chat_id": 5, "caption": None},
                                "photo", "p.jpg", b"JPG", "image/jpeg")
    assert out == {"ok": True}
    assert captured["url"] == "https://example.invalid/sendPhoto"
    boundary = captured["headers"]["Content-Type"].split("boundary=")[1]
    body = captured["data"]
    assert body.startswith(("--" + boundary).encode()) and body.endswith(("--" + boundary + "--\r\n").encode())
    assert b'name="chat_id"\r\n\r\n5\r\n' in body and b"caption" not in body
    assert b'name="photo"; filename="p.jpg"\r\nContent-Type: image/jpeg\r\n\r\nJPG\r\n' in body
