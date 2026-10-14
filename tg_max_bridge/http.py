"""Minimal JSON-over-HTTPS client on urllib."""

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

USER_AGENT = "tg-max-bridge/" + __version__


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

    def get(self, path, params=None, timeout=None):
        return self._request("GET", path, params, None, timeout)

    def post(self, path, payload, params=None):
        return self._request("POST", path, params, payload, None)

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
            with urllib.request.urlopen(
                req, timeout=timeout or self.timeout, context=self.context
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            raise HttpError(e.code, body) from None
