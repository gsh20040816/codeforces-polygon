"""Thin Codeforces Polygon API client.

Every API method is reached through ``Polygon.call(method, **params)``.
Requests are sent the same way as Polygon's reference tooling: a multipart
POST whose fields are all signed with ``apiSig``.  Errors are raised as
``PolygonError`` and never swallowed.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import string
import time
from typing import Any

import requests

DEFAULT_URL = "https://polygon.codeforces.com"
TIMEOUT_SECONDS = 120


class PolygonError(Exception):
    """Polygon rejected a request, or the request could not be made.

    ``status`` is the HTTP status code when the error came from an HTTP response.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _to_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bool):
        return b"true" if value else b"false"
    return str(value).encode("utf-8")


def sign(method: str, fields: dict[str, bytes], secret: str, rand: str | None = None) -> bytes:
    """Return the ``apiSig`` value for ``fields``.

    ``rand/method?k1=v1&k2=v2#secret`` with params sorted by (key, value),
    hashed with SHA-512 and prefixed by the 6-character ``rand``.
    """
    if rand is None:
        rand = "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
    query = b"&".join(key.encode() + b"=" + value for key, value in sorted(
        (key, value) for key, value in fields.items()
    ))
    base = rand.encode() + b"/" + method.encode() + b"?" + query + b"#" + secret.encode()
    return rand.encode() + hashlib.sha512(base).hexdigest().encode()


def _envelope(response: requests.Response) -> dict | None:
    """The ``{"status": ...}`` JSON envelope, or None for any other body.

    Polygon labels JSON as text/html, so the body is inspected instead of Content-Type.
    """
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) and "status" in data else None


def _failure_message(method: str, response: requests.Response) -> str:
    data = _envelope(response) or {}
    if data.get("comment"):
        details = data.get("result")  # e.g. DeleteTestsResult explaining which tests failed
        return f"{method}: {data['comment']}" + (f" {json.dumps(details, ensure_ascii=False)}" if details else "")
    text = response.text.strip()
    return f"{method}: HTTP {response.status_code}" + (f": {text[:300]}" if text else "")


class Polygon:
    def __init__(self, key: str, secret: str, url: str = DEFAULT_URL):
        self.key = key
        self.secret = secret
        self.url = url.rstrip("/")

    @classmethod
    def from_env(cls) -> "Polygon":
        key = os.environ.get("POLYGON_API_KEY")
        secret = os.environ.get("POLYGON_API_SECRET")
        if not key or not secret:
            raise PolygonError(
                "POLYGON_API_KEY and POLYGON_API_SECRET must be set "
                "(create them at https://polygon.codeforces.com/settings)"
            )
        return cls(key, secret, os.environ.get("POLYGON_URL", DEFAULT_URL))

    def call(self, method: str, *, raw: bool | None = False, **params: Any) -> Any:
        """Call an API method.  ``None`` params are omitted.

        Returns the ``result`` field of the JSON response.  ``raw=True`` returns
        the body as bytes (file/test/package downloads); ``raw=None`` decides
        from the body: a JSON status envelope is parsed, anything else that came
        back with HTTP 200 is returned as bytes (for ``polygonctl call``).
        With ``raw=False`` a body that is not an envelope is an error.
        """
        fields = {key: _to_bytes(value) for key, value in params.items() if value is not None}
        fields["apiKey"] = self.key.encode()
        fields["time"] = str(int(time.time())).encode()
        fields["apiSig"] = sign(method, fields, self.secret)

        response = requests.post(
            f"{self.url}/api/{method}", files=fields, timeout=TIMEOUT_SECONDS
        )
        if raw and response.status_code == 200:
            return response.content
        data = _envelope(response)
        if data is None:
            if raw is None and response.status_code == 200:
                return response.content  # a file, test or script body
            raise PolygonError(_failure_message(method, response), response.status_code)
        if data.get("status") != "OK":
            raise PolygonError(_failure_message(method, response), response.status_code)
        return data.get("result")


def download(url: str, login: str, password: str, **params: Any) -> bytes:
    """Download a file through Polygon's web form (login/password, not API keys).

    Used for problem packages by URL, problem.xml, contest.xml and
    statements PDFs, which the API does not expose.
    """
    data = {"login": login, "password": password}
    data.update({key: str(value) for key, value in params.items() if value is not None})
    response = requests.post(url, data=data, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    if response.headers.get("Content-Type", "").startswith("text/html"):
        raise PolygonError(
            f"{url}: got an HTML page instead of a file "
            "(wrong POLYGON_LOGIN/POLYGON_PASSWORD, URL, or missing --pin?)"
        )
    return response.content
