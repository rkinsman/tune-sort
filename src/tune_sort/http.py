"""The real Fetch: httpx with a per-host rate limit."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from tune_sort.sources import Fetch, FetchError

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def make_fetch(min_interval: float = 1.0, timeout: float = 15.0) -> Fetch:
    """Return a Fetch that waits at least `min_interval` seconds between requests to the
    same host and raises FetchError on network errors or non-2xx responses."""
    client = httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
    )
    last_request: dict[str, float] = {}

    def fetch(url: str) -> str:
        host = urlsplit(url).netloc
        wait = last_request.get(host, 0.0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last_request[host] = time.monotonic()
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise FetchError(f"{url}: {e}") from e
        return response.text

    return fetch
