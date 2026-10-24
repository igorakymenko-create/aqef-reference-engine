"""HTTP subject transport. Wire contract: docs/PROVIDERS.md."""
import json
import os
from urllib.parse import urlsplit

import httpx
from pydantic import Field, StrictBool, StrictStr

from engine.models.base import AQEFBaseModel


class SubjectReply(AQEFBaseModel):
    response: StrictStr
    complete: StrictBool = True
    artifacts: dict = Field(default_factory=dict)
    usage: dict = Field(default_factory=dict)


def load_provider_urls():
    try:
        value = json.loads(os.environ.get("AQEF_PROVIDER_URLS", "{}"))
    except ValueError as exc:
        raise ValueError("AQEF_PROVIDER_URLS must be a JSON object") from exc
    if not isinstance(value, dict):
        raise ValueError("AQEF_PROVIDER_URLS must be an identifier-to-URL object")
    for key, url in value.items():
        if not isinstance(key, str) or not key or not isinstance(url, str):
            raise ValueError("Provider identifiers and URLs must be nonempty strings")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.fragment or parsed.username:
            raise ValueError(f"Invalid provider URL for '{key}'")
    return value


class HTTPProvider:
    def __init__(self, urls):
        self.urls = dict(urls)

    async def call(self, model, payload, timeout):
        # No redirects or HTTP-level retries: a redirect may repeat a real invocation.
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            reply = await client.post(self.urls[model], json=payload)
            reply.raise_for_status()
            return reply.json()
