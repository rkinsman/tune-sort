"""Ultimate Guitar lookup from public pages.

Bass order: the highest-rated bass-only Pro tab, then the highest-rated Bass tab. Official
tabs and multi-instrument Pro tabs are skipped, since their public pages only give the
first (usually guitar) track's tuning.

Guitar order: the highest-rated Pro tab whose meta.instruments mentions "guitar" and whose
meta.tuning parses as a guitar tuning (source "ug-pro"), then the highest-rated "Tabs"
result with a guitar meta.tuning (source "ug-tab"). Search paging stops once matching
results of the instrument's tab type ("Bass Tabs" or "Tabs") have been found.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Callable, Sequence
from typing import Any, Optional
from urllib.parse import urlencode

from tune_sort import matching
from tune_sort.sources import Fetch, FetchError, Match
from tune_sort.tuning import Instrument, parse_note_names

SEARCH_URL = "https://www.ultimate-guitar.com/search.php"
MAX_PAGES_PER_TYPE = 3  # tab pages fetched per tab type before giving up on it
MAX_SEARCH_PAGES = 3  # search result pages read while looking for the instrument's tabs

# Per instrument: (tab type, Match.source, page check) steps in order, and the tab type
# whose presence in the search results stops paging.
_PAGE_CHECKS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "bass-only": lambda meta: (
        meta.get("instrumentsCount") == 1 and "bass" in str(meta.get("instruments") or "").lower()
    ),
    "has-guitar": lambda meta: "guitar" in str(meta.get("instruments") or "").lower(),
    "any": lambda meta: True,
}
_STEPS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "bass": (("Pro", "ug-pro", "bass-only"), ("Bass Tabs", "ug-bass", "any")),
    "guitar": (("Pro", "ug-pro", "has-guitar"), ("Tabs", "ug-tab", "any")),
}
_TAB_TYPE = {"bass": "Bass Tabs", "guitar": "Tabs"}

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


# kinds: "pro" is the Pro-tab step, "tab" the Bass tab (bass) or Tab (guitar) step.
KINDS = ("pro", "tab")


class UltimateGuitar:
    """With the default kinds, `name` is "ug" and both steps are tried in order. With a
    single kind it is one orderable source: name "ug-pro", or "ug-bass" / "ug-tab" for
    the "tab" kind, and lookup only uses that step (same search, ranking, paging and
    exact-before-similar rules)."""

    def __init__(
        self, fetch: Fetch, instrument: Instrument = "bass", kinds: Sequence[str] = KINDS
    ) -> None:
        unknown = set(kinds) - set(KINDS)
        if unknown or not kinds:
            raise ValueError(f"kinds must be taken from {KINDS}, got {tuple(kinds)}")
        self._kinds = tuple(kinds)
        if self._kinds == KINDS:
            self.name = "ug"
        else:
            self.name = "-".join(_STEPS[instrument][KINDS.index(k)][1] for k in self._kinds)
        self._fetch = fetch
        self.instrument: Instrument = instrument

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        def matches(r: dict[str, Any], test: Any) -> bool:
            return bool(test(artist, title, r.get("artist_name") or "", r.get("song_name") or ""))

        exact: list[dict[str, Any]] = []
        similar: list[dict[str, Any]] = []
        # Results are paginated and Bass tabs often only start on a later page.
        tab_type = _TAB_TYPE[self.instrument]
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
            if any(r.get("type") == tab_type for r in exact + similar):
                break
            pagination = data.get("pagination")
            total = pagination.get("total") if isinstance(pagination, dict) else None
            if not isinstance(total, int) or page + 1 > total:
                break
        return self._best(exact, exact=True) or self._best(similar, exact=False)

    def _best(self, results: list[dict[str, Any]], exact: bool) -> Optional[Match]:
        steps = [_STEPS[self.instrument][KINDS.index(k)] for k in self._kinds]
        for tab_type, source, check in steps:
            for r in _rank(results, tab_type)[:MAX_PAGES_PER_TYPE]:
                match = self._from_tab(r, source, check, exact)
                if match:
                    return match
        return None

    def _from_tab(
        self, result: dict[str, Any], source: str, check: str, exact: bool
    ) -> Optional[Match]:
        url = str(result["tab_url"])
        try:
            meta = _page_data(self._fetch(url))["tab_view"]["meta"]
            if not _PAGE_CHECKS[check](meta):
                return None
            tuning = parse_note_names(str(meta["tuning"]["value"]), self.instrument)
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
