"""HTTP transport shared by every SDK operation."""

from collections.abc import Mapping
from urllib.parse import quote

import httpx


class APIError(Exception):
    """An HTTP error with its original status and response bytes."""

    def __init__(self, response: httpx.Response):
        self.status_code = response.status_code
        self.body = response.content
        self.response = response
        super().__init__(f"AQEF HTTP {self.status_code}")


class TransportError(Exception):
    """No API response was received because the HTTP exchange failed."""


UNSET = object()


def segment(value: str) -> str:
    return quote(value, safe="")


class Transport:
    def __init__(self, url: str, token: str, *, timeout: float = 60.0):
        try:
            self._http = httpx.Client(
                base_url=url, headers={"Authorization": f"Bearer {token}"},
                timeout=timeout, follow_redirects=False,
            )
        except (httpx.InvalidURL, UnicodeError):
            raise TransportError("Invalid AQEF URL or bearer token") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        self._http.close()

    def request(
        self, method: str, path: str, *,
        params: Mapping | None = None, headers: Mapping | None = None,
        body: object = UNSET,
    ) -> httpx.Response:
        """Send an API-relative request and return the original HTTP response."""
        url = httpx.URL(path)
        if not path.startswith("/") or path.startswith("//") or url.host or url.scheme:
            raise ValueError("Expected an API-relative path starting with /")
        outgoing = {key: value for key, value in (headers or {}).items() if value is not None}
        query = {key: value for key, value in (params or {}).items() if value is not None}
        options = {}
        if body is None:
            # HTTPX otherwise interprets json=None as no body.
            options["content"] = b"null"
            outgoing.setdefault("Content-Type", "application/json")
        elif body is not UNSET:
            options["json"] = body
        try:
            response = self._http.request(
                method, path, params=query or None, headers=outgoing, **options,
            )
        except (httpx.RequestError, httpx.InvalidURL):
            raise TransportError("AQEF transport error or timeout") from None
        if response.is_error:
            raise APIError(response)
        return response
