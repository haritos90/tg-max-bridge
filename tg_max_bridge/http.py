"""Minimal JSON-over-HTTPS client on urllib."""

import http.client
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = "tg-max-bridge/" + __version__
CONNECT_TIMEOUT = 10  # seconds per address; the read timeout is separate


class _Connection(http.client.HTTPSConnection):
    """IPv4 first, short connect timeout per address."""

    def connect(self):
        infos = socket.getaddrinfo(self.host, self.port, 0, socket.SOCK_STREAM)
        infos.sort(key=lambda i: i[0] != socket.AF_INET)
        err = None
        for family, kind, proto, _, addr in infos:
            sock = socket.socket(family, kind, proto)
            sock.settimeout(CONNECT_TIMEOUT)
            try:
                sock.connect(addr)
                break
            except OSError as e:
                err = e
                sock.close()
        else:
            raise err or OSError("no address for %s" % self.host)
        sock.settimeout(self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _Handler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Connection, req, context=self._context)


class HttpError(Exception):
    """Non-2xx response, carrying the status and body."""

    def __init__(self, status, body):
        super().__init__("HTTP %s: %s" % (status, body[:300]))
        self.status = status
        self.body = body


class JsonClient:
    """Base URL plus fixed headers; one SSL context."""

    def __init__(self, base_url, headers=None, ca_file=None, timeout=60):
        self.base_url = base_url.rstrip("/")
        self.headers = {"User-Agent": USER_AGENT, **(headers or {})}
        self.timeout = timeout
        self.context = ssl.create_default_context()
        if ca_file:
            # The API host may chain to a root outside the system store.
            self.context.load_verify_locations(cafile=ca_file)
        self.opener = urllib.request.build_opener(_Handler(context=self.context))

    def get(self, path, params=None, timeout=None):
        return self._request("GET", path, params, None, timeout)

    def post(self, path, payload, params=None):
        return self._request("POST", path, params, payload, None)

    def patch(self, path, payload, params=None):
        return self._request("PATCH", path, params, payload, None)

    def _request(self, method, path, params, payload, timeout):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        data = None
        headers = dict(self.headers)
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise HttpError(e.code, body) from None
