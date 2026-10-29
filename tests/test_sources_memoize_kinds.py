"""`memoize` and the orderable Ultimate Guitar sources (the `kinds` parameter)."""
from __future__ import annotations

from typing import List

import pytest

from tests.conftest import (
    FakeFetch,
    T,
    fixture_text,
    ug_result,
    ug_search_page,
    ug_tab_page,
)
from tune_sort.sources import FetchError, memoize
from tune_sort.sources.songsterr import Songsterr
from tune_sort.sources.ultimate_guitar import SEARCH_URL, UltimateGuitar

PRO_554368 = "https://tabs.ultimate-guitar.com/tab/tool/schism-guitar-pro-554368"
BASS_127745 = "https://tabs.ultimate-guitar.com/tab/tool/schism-bass-127745"


# --------------------------------------------------------------------- memoize


class Counting:
    def __init__(self, responses):
        self.responses = responses
        self.calls: List[str] = []

    def __call__(self, url):
        self.calls.append(url)
        value = self.responses[url]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_memoize_fetches_each_url_once():
    inner = Counting({"u1": "body1"})
    fetch = memoize(inner)
    assert fetch("u1") == "body1"
    assert fetch("u1") == "body1"
    assert fetch("u1") == "body1"
    assert inner.calls == ["u1"]


def test_memoize_different_urls_fetched_separately():
    inner = Counting({"u1": "a", "u2": "b"})
    fetch = memoize(inner)
    assert fetch("u1") == "a"
    assert fetch("u2") == "b"
    assert fetch("u1") == "a"
    assert inner.calls == ["u1", "u2"]


def test_memoize_does_not_store_errors():
    inner = Counting({"u1": [FetchError("down"), "body"]})
    fetch = memoize(inner)
    with pytest.raises(FetchError):
        fetch("u1")
    assert fetch("u1") == "body"
    assert fetch("u1") == "body"
    assert inner.calls == ["u1", "u1"]


def test_memoize_passes_errors_through_each_time():
    inner = Counting({"u1": [FetchError("a"), FetchError("b")]})
    fetch = memoize(inner)
    for _ in range(2):
        with pytest.raises(FetchError):
            fetch("u1")
    assert inner.calls == ["u1", "u1"]


# ------------------------------------------------------------ source names


def test_default_names():
    assert UltimateGuitar(FakeFetch()).name == "ug"
    assert UltimateGuitar(FakeFetch(), "guitar").name == "ug"
    assert UltimateGuitar(FakeFetch(), "bass", ("pro", "tab")).name == "ug"


def test_pro_only_name():
    assert UltimateGuitar(FakeFetch(), "bass", ("pro",)).name == "ug-pro"
    assert UltimateGuitar(FakeFetch(), "guitar", ("pro",)).name == "ug-pro"


def test_tab_only_name_depends_on_instrument():
    assert UltimateGuitar(FakeFetch(), "bass", ("tab",)).name == "ug-bass"
    assert UltimateGuitar(FakeFetch(), "guitar", ("tab",)).name == "ug-tab"


def test_songsterr_name():
    assert Songsterr(FakeFetch()).name == "songsterr"
    assert Songsterr(FakeFetch(), "guitar").name == "songsterr"


# --------------------------------------------------------- real Schism fixtures

# The real search page lists more Pro tabs than we have saved; any other Pro tab is served
# as a guitar-only page (skipped for bass, a valid but different candidate for guitar).
OTHER_PRO = ug_tab_page("E A D G B E", "lead guitar", 1)


def schism_fetch():
    return FakeFetch(
        {
            PRO_554368: fixture_text("ug/pro_554368.html"),
            BASS_127745: fixture_text("ug/bass_127745.html"),
        },
        SEARCH_URL,
        fixture_text("ug/search_tool_schism.html"),
        extra_pro_page=OTHER_PRO,
    )


def test_bass_pro_only_returns_none_on_schism():
    fetch = schism_fetch()
    assert UltimateGuitar(fetch, "bass", ("pro",)).lookup("Tool", "Schism") is None
    assert BASS_127745 not in fetch.calls


def test_bass_tab_only_returns_ug_bass_without_fetching_pro_pages():
    fetch = schism_fetch()
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")
    assert m.url == BASS_127745
    assert fetch.tab_calls() == [BASS_127745]


def test_guitar_pro_only_returns_ug_pro_drop_d_on_schism():
    fetch = schism_fetch()
    m = UltimateGuitar(fetch, "guitar", ("pro",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.tuning == T("D A D G B E", "guitar")
    assert m.url == PRO_554368


def test_default_kinds_unchanged_on_schism():
    m = UltimateGuitar(schism_fetch()).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    m2 = UltimateGuitar(schism_fetch(), "guitar").lookup("Tool", "Schism")
    assert m2 is not None
    assert m2.source == "ug-pro"


# ------------------------------------------------------------ synthetic checks


def url(id, kind):
    return "https://tabs.ultimate-guitar.com/tab/tool/schism-%s-%s" % (kind, id)


def result(id, type_, kind, rating=4.0):
    r = ug_result(id, type_, rating, 10)
    r["tab_url"] = url(id, kind)
    return r


def make(results, pages, instrument, kinds):
    fetch = FakeFetch(pages, SEARCH_URL, ug_search_page(results))
    return UltimateGuitar(fetch, instrument, kinds), fetch


def test_guitar_tab_only_ignores_pro_results():
    ug, fetch = make(
        [result(1, "Pro", "guitar-pro", 5.0), result(2, "Tabs", "tabs")],
        {
            url(1, "guitar-pro"): ug_tab_page("D A D G B E", "lead guitar", 1),
            url(2, "tabs"): ug_tab_page("E A D G B E", "guitar", 1),
        },
        "guitar",
        ("tab",),
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert m.url == url(2, "tabs")
    assert fetch.tab_calls() == [url(2, "tabs")]


def test_guitar_pro_only_ignores_tabs_results():
    ug, fetch = make(
        [result(2, "Tabs", "tabs", 5.0)],
        {url(2, "tabs"): ug_tab_page("E A D G B E", "guitar", 1)},
        "guitar",
        ("pro",),
    )
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


def test_guitar_pro_only_returns_pro():
    ug, _ = make(
        [result(1, "Pro", "guitar-pro"), result(2, "Tabs", "tabs", 5.0)],
        {
            url(1, "guitar-pro"): ug_tab_page("D A D G B E", "lead guitar", 1),
            url(2, "tabs"): ug_tab_page("E A D G B E", "guitar", 1),
        },
        "guitar",
        ("pro",),
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.url == url(1, "guitar-pro")


def test_bass_pro_only_uses_bass_only_pro_page():
    ug, _ = make(
        [result(1, "Pro", "guitar-pro"), result(2, "Bass Tabs", "bass", 5.0)],
        {
            url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1),
            url(2, "bass"): ug_tab_page("D A D G"),
        },
        "bass",
        ("pro",),
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.tuning == T("E A D G")


def test_bass_tab_only_ignores_bass_only_pro_page():
    ug, fetch = make(
        [result(1, "Pro", "guitar-pro", 5.0), result(2, "Bass Tabs", "bass")],
        {
            url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1),
            url(2, "bass"): ug_tab_page("D A D G"),
        },
        "bass",
        ("tab",),
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")
    assert fetch.tab_calls() == [url(2, "bass")]


def test_exact_before_similar_with_single_kind():
    ug, _ = make(
        [
            result(1, "Bass Tabs", "bass", 5.0) | {"song_name": "Schism (Live)"},
            result(2, "Bass Tabs", "bass", 3.0),
        ],
        {url(1, "bass"): ug_tab_page("C G C F"), url(2, "bass"): ug_tab_page("D A D G")},
        "bass",
        ("tab",),
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is True
    assert m.url == url(2, "bass")
