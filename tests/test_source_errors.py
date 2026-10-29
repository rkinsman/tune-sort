"""Fetch failures raise SourceError; parse problems still give None / skip."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import pytest

from tests.conftest import FakeFetch, store_page, ug_result, ug_search_page, ug_tab_page
from tune_sort.sources import FetchError, SourceError
from tune_sort.sources.songsterr import SEARCH_URL as SONGSTERR_SEARCH_URL
from tune_sort.sources.songsterr import Songsterr
from tune_sort.sources.ultimate_guitar import SEARCH_URL, UltimateGuitar


def tab_url(id, kind="bass"):
    return "https://tabs.ultimate-guitar.com/tab/tool/schism-%s-%s" % (kind, id)


def pro(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Pro", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "guitar-pro")
    return r


def bass(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Bass Tabs", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "bass")
    return r


def tabs(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Tabs", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "tabs")
    return r


class PagedFetch:
    def __init__(self, search_pages: Dict[int, Any], tab_pages: Optional[Dict[str, Any]] = None):
        self.search_pages = search_pages
        self.tab_pages = tab_pages or {}
        self.search_page_requests: List[int] = []

    def __call__(self, url: str) -> str:
        if url.startswith(SEARCH_URL):
            page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
            self.search_page_requests.append(page)
            value = self.search_pages.get(page, FetchError("no such page"))
        else:
            value = self.tab_pages.get(url, FetchError("unknown url: " + url))
        if isinstance(value, Exception):
            raise value
        return str(value)


def paged(results, total=None, current=1):
    data: Dict[str, Any] = {"search_query": "q", "results": results}
    if total is not None:
        data["pagination"] = {"total": total, "current": current}
    return store_page(data)


def test_source_error_is_an_exception():
    assert issubclass(SourceError, Exception)


# -------------------------------------------------------------------------- UG


@pytest.mark.parametrize("instrument", ["bass", "guitar"])
def test_ug_search_fetch_error_raises(instrument):
    fetch = FakeFetch({}, SEARCH_URL, FetchError("down"))
    with pytest.raises(SourceError):
        UltimateGuitar(fetch, instrument).lookup("Tool", "Schism")


@pytest.mark.parametrize("kinds", [("pro",), ("tab",), ("pro", "tab")])
def test_ug_search_fetch_error_raises_for_every_kind(kinds):
    fetch = FakeFetch({}, SEARCH_URL, FetchError("down"))
    with pytest.raises(SourceError):
        UltimateGuitar(fetch, "bass", kinds).lookup("Tool", "Schism")


def test_ug_tab_page_fetch_error_raises():
    fetch = FakeFetch({tab_url(1): FetchError("boom")}, SEARCH_URL, ug_search_page([bass(1)]))
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")


def test_ug_fetch_error_on_a_lower_ranked_tab_page_raises_if_it_is_reached():
    fetch = FakeFetch(
        {tab_url(1): ug_tab_page(with_tuning=False), tab_url(2): FetchError("boom")},
        SEARCH_URL,
        ug_search_page([bass(1, 4.9), bass(2, 4.0)]),
    )
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")


def test_ug_pro_tab_page_fetch_error_raises():
    fetch = FakeFetch(
        {tab_url(1, "guitar-pro"): FetchError("boom"), tab_url(2): ug_tab_page("D A D G")},
        SEARCH_URL,
        ug_search_page([pro(1), bass(2)]),
    )
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")


def test_ug_guitar_tab_page_fetch_error_raises():
    fetch = FakeFetch(
        {tab_url(1, "tabs"): FetchError("boom")}, SEARCH_URL, ug_search_page([tabs(1)])
    )
    with pytest.raises(SourceError):
        UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")


def test_ug_fetch_error_on_search_page_two_raises():
    fetch = PagedFetch(
        {1: paged([pro(1)], total=3), 2: FetchError("down")},
        {tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1)},
    )
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert fetch.search_page_requests == [1, 2]


def test_ug_fetch_error_on_search_page_three_raises():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=9),
            2: paged([pro(2)], total=9, current=2),
            3: FetchError("down"),
        },
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "guitar", 1),
            tab_url(2, "guitar-pro"): ug_tab_page("E A D G", "guitar", 1),
        },
    )
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")


def test_ug_page_two_error_with_nothing_usable_raises():
    fetch = PagedFetch({1: paged([pro(1)], total=3), 2: FetchError("down")})
    with pytest.raises(SourceError):
        UltimateGuitar(fetch).lookup("Tool", "Schism")


def test_ug_parse_problems_still_return_none():
    for response in ("<html><body>captcha</body></html>", store_page({"something": "else"})):
        fetch = FakeFetch({}, SEARCH_URL, response)
        assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None


def test_ug_tab_page_parse_problems_still_skipped():
    fetch = FakeFetch(
        {
            tab_url(1): "<html>nothing</html>",
            tab_url(2): ug_tab_page(with_tuning=False),
            tab_url(3): ug_tab_page("not a tuning"),
            tab_url(4): ug_tab_page("D A D G"),
        },
        SEARCH_URL,
        ug_search_page([bass(1, 4.9), bass(2, 4.8), bass(3, 4.7), bass(4, 4.6)]),
    )
    # Three tab pages per type are tried; the fourth (usable) one is never reached.
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is None
    assert fetch.tab_calls() == [tab_url(1), tab_url(2), tab_url(3)]


def test_ug_unparseable_page_two_does_not_raise():
    fetch = PagedFetch(
        {1: paged([pro(1)], total=3), 2: "<html>captcha</html>"},
        {tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1)},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"


# ------------------------------------------------------------------- Songsterr


@pytest.mark.parametrize("instrument", ["bass", "guitar"])
def test_songsterr_fetch_error_raises(instrument):
    fetch = FakeFetch({}, SONGSTERR_SEARCH_URL, FetchError("down"))
    with pytest.raises(SourceError):
        Songsterr(fetch, instrument).lookup("Tool", "Schism")


def test_songsterr_invalid_json_still_returns_none():
    fetch = FakeFetch({}, SONGSTERR_SEARCH_URL, "<html>not json</html>")
    assert Songsterr(fetch).lookup("Tool", "Schism") is None


def test_songsterr_unexpected_layout_still_returns_none():
    fetch = FakeFetch({}, SONGSTERR_SEARCH_URL, json.dumps({"not": "a list"}))
    assert Songsterr(fetch).lookup("Tool", "Schism") is None
