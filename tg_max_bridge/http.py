"""Minimal JSON-over-HTTPS client on urllib."""

import http.client
import json
import socket
import uuid
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

    def get_bytes(self, url):
        """Body and content type of an absolute URL."""
        return self._raw("GET", url, None, {}, None)

    def post_multipart(self, url, fields, name, filename, data, mime):
        """One file plus text fields; url absolute or a path; JSON back."""
        if url.startswith("/"):
            url = self.base_url + url
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                          % (boundary, key, value)).encode("utf-8"))
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                      "Content-Type: %s\r\n\r\n" % (boundary, name, filename, mime)).encode("utf-8"))
        parts.append(data)
        parts.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        body, _ = self._raw("POST", url, b"".join(parts),
                            {"Content-Type": "multipart/form-data; boundary=" + boundary}, None)
        try:
            return json.loads(body.decode("utf-8")) if body else {}
        except ValueError:
            # An upload host may answer with plain text.
            return {"raw": body.decode("utf-8", "replace")}

    def _request(self, method, path, params, payload, timeout):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        body, _ = self._raw(method, url, data, headers, timeout)
        return json.loads(body.decode("utf-8"))

    def _raw(self, method, url, data, extra_headers, timeout):
        headers = dict(self.headers)
        headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout or self.timeout) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise HttpError(e.code, body) from None
