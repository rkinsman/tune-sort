"""Ultimate Guitar lookup from public pages.

Order: the highest-rated bass-only Pro tab, then the highest-rated Bass tab. Official tabs
and multi-instrument Pro tabs are skipped, since their public pages only give the first
(usually guitar) track's tuning.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Optional
from urllib.parse import urlencode

from tune_sort import matching
from tune_sort.sources import Fetch, FetchError, Match
from tune_sort.tuning import parse_note_names

SEARCH_URL = "https://www.ultimate-guitar.com/search.php"
MAX_PAGES_PER_TYPE = 3  # tab pages fetched per tab type before giving up on it
MAX_SEARCH_PAGES = 3  # search result pages read while looking for Bass tabs

_STORE = re.compile(r'class="js-store"[^>]*?data-content="([^"]*)"')


def search_url(artist: str, title: str, page: int = 1) -> str:
    """URL of the UG title search for "<artist> <title>"; pages after the first add page=N."""
    params: dict[str, object] = {"search_type": "title", "value": f"{artist} {title}"}
    if page > 1:
        params["page"] = page
    return SEARCH_URL + "?" + urlencode(params)


def parse_store(html: str) -> dict[str, Any]:
    """Return the JSON in the page's `js-store` element's data-content attribute."""
    m = _STORE.search(html)
    if m is None:
        raise ValueError("page has no js-store")
    data = json.loads(html_lib.unescape(m.group(1)))
    if not isinstance(data, dict):
        raise ValueError("js-store is not an object")
    return data


def _page_data(html: str) -> dict[str, Any]:
    data: Any = parse_store(html)
    page = data["store"]["page"]["data"]
    if not isinstance(page, dict):
        raise ValueError("unexpected js-store layout")
    return page


def _rank(results: list[dict[str, Any]], tab_type: str) -> list[dict[str, Any]]:
    of_type = [r for r in results if r.get("type") == tab_type and r.get("tab_url")]
    return sorted(of_type, key=lambda r: (r.get("rating") or 0, r.get("votes") or 0), reverse=True)


class UltimateGuitar:
    name = "ug"

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        def matches(r: dict[str, Any], test: Any) -> bool:
            return bool(test(artist, title, r.get("artist_name") or "", r.get("song_name") or ""))

        exact: list[dict[str, Any]] = []
        similar: list[dict[str, Any]] = []
        # Results are paginated and Bass tabs often only start on a later page.
        for page in range(1, MAX_SEARCH_PAGES + 1):
            try:
                data = _page_data(self._fetch(search_url(artist, title, page)))
                results = data.get("results")
                if not isinstance(results, list):
                    raise ValueError("search page has no results list")
            except (FetchError, ValueError, KeyError, TypeError):
                if page == 1:
                    return None
                break
            for r in results:
                if not isinstance(r, dict):
                    continue
                if matches(r, matching.is_exact):
                    exact.append(r)
                elif matches(r, matching.is_similar):
                    similar.append(r)
            if any(r.get("type") == "Bass Tabs" for r in exact + similar):
                break
            pagination = data.get("pagination")
            total = pagination.get("total") if isinstance(pagination, dict) else None
            if not isinstance(total, int) or page + 1 > total:
                break
        return self._best(exact, exact=True) or self._best(similar, exact=False)

    def _best(self, results: list[dict[str, Any]], exact: bool) -> Optional[Match]:
        steps = (("Pro", "ug-pro", True), ("Bass Tabs", "ug-bass", False))
        for tab_type, source, bass_only in steps:
            for r in _rank(results, tab_type)[:MAX_PAGES_PER_TYPE]:
                match = self._from_tab(r, source, bass_only, exact)
                if match:
                    return match
        return None

    def _from_tab(
        self, result: dict[str, Any], source: str, bass_only: bool, exact: bool
    ) -> Optional[Match]:
        url = str(result["tab_url"])
        try:
            meta = _page_data(self._fetch(url))["tab_view"]["meta"]
            if bass_only and not (
                meta.get("instrumentsCount") == 1
                and "bass" in str(meta.get("instruments") or "").lower()
            ):
                return None
            tuning = parse_note_names(str(meta["tuning"]["value"]))
        except (FetchError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return Match(
            tuning=tuning,
            source=source,
            url=url,
            matched_artist=str(result.get("artist_name") or ""),
            matched_title=str(result.get("song_name") or ""),
            exact=exact,
        )
