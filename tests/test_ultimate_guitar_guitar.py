"""Ultimate Guitar lookups in guitar mode (and instrument attribute checks)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from conftest import (
    FakeFetch,
    T,
    fixture_text,
    store_page,
    ug_result,
    ug_search_page,
    ug_tab_page,
)

from tune_sort.sources import FetchError
from tune_sort.sources.ultimate_guitar import MAX_PAGES_PER_TYPE, SEARCH_URL, UltimateGuitar

PRO_554368 = "https://tabs.ultimate-guitar.com/tab/tool/schism-guitar-pro-554368"
BASS_127745 = "https://tabs.ultimate-guitar.com/tab/tool/schism-bass-127745"


def tab_url(id, kind):
    return "https://tabs.ultimate-guitar.com/tab/tool/schism-%s-%s" % (kind, id)


def pro(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Pro", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "guitar-pro")
    return r


def tabs(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Tabs", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "tabs")
    return r


def bass(id, rating=4.0, votes=10, **kw):
    r = ug_result(id, "Bass Tabs", rating, votes, **kw)
    r["tab_url"] = tab_url(id, "bass")
    return r


def pro_page(value="E A D G B E", instruments="lead guitar", count=1):
    return ug_tab_page(value, instruments, count)


def tab_page(value="E A D G B E"):
    return ug_tab_page(value, "guitar", 1)


def gmake(results, pages=None):
    fetch = FakeFetch(pages, SEARCH_URL, ug_search_page(results))
    return UltimateGuitar(fetch, "guitar"), fetch


# --------------------------------------------------------------- real fixtures


def test_real_pro_fixture_gives_guitar_drop_d():
    fetch = FakeFetch(
        {PRO_554368: fixture_text("ug/pro_554368.html")},
        SEARCH_URL,
        fixture_text("ug/search_tool_schism.html"),
    )
    m = UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.tuning == T("D A D G B E", "guitar")
    assert m.tuning.name == "Drop D"
    assert m.tuning.instrument == "guitar"
    assert m.url == PRO_554368
    assert m.exact is True
    assert fetch.tab_calls() == [PRO_554368]


def test_real_pro_fixture_still_skipped_in_bass_mode():
    fetch = FakeFetch(
        {
            PRO_554368: fixture_text("ug/pro_554368.html"),
            BASS_127745: fixture_text("ug/bass_127745.html"),
        },
        SEARCH_URL,
        fixture_text("ug/search_tool_schism.html"),
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")
    assert m.tuning.instrument == "bass"


def test_instrument_attribute():
    assert UltimateGuitar(FakeFetch()).instrument == "bass"
    assert UltimateGuitar(FakeFetch(), "bass").instrument == "bass"
    assert UltimateGuitar(FakeFetch(), "guitar").instrument == "guitar"


# ------------------------------------------------------------------- Pro tabs


def test_pro_tab_with_guitar_tuning():
    ug, _ = gmake([pro(1)], {tab_url(1, "guitar-pro"): pro_page("E A D G B E")})
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.tuning == T("E A D G B E", "guitar")
    assert m.tuning.string_count == 6
    assert m.url == tab_url(1, "guitar-pro")
    assert m.matched_artist == "Tool"
    assert m.matched_title == "Schism"


def test_pro_instruments_matched_case_insensitively():
    ug, _ = gmake([pro(1)], {tab_url(1, "guitar-pro"): pro_page("D A D G B E", "Lead GUITAR")})
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"


def test_pro_multi_instrument_page_mentioning_guitar_accepted():
    page = pro_page("D A D G B E", "lead guitar, bass and percussion", 4)
    ug, _ = gmake([pro(1)], {tab_url(1, "guitar-pro"): page})
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.tuning.name == "Drop D"


def test_pro_without_guitar_in_instruments_skipped_for_tabs_fallback():
    ug, _ = gmake(
        [pro(1, 4.9), tabs(2)],
        {
            tab_url(1, "guitar-pro"): pro_page("E A D G B E", "bass"),
            tab_url(2, "tabs"): tab_page("D A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert m.url == tab_url(2, "tabs")


def test_pro_with_bass_tuning_skipped():
    ug, _ = gmake(
        [pro(1, 4.9), tabs(2)],
        {
            tab_url(1, "guitar-pro"): pro_page("E A D G", "guitar"),
            tab_url(2, "tabs"): tab_page("D A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert m.tuning == T("D A D G B E", "guitar")


def test_pro_ranked_by_rating_then_votes():
    ug, fetch = gmake(
        [pro(1, 4.0, 500), pro(2, 4.9, 5), pro(3, 4.9, 50)],
        {
            tab_url(1, "guitar-pro"): pro_page("E A D G B E"),
            tab_url(2, "guitar-pro"): pro_page("D A D G B E"),
            tab_url(3, "guitar-pro"): pro_page("D A D G A D"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.tuning.name == "DADGAD"
    assert fetch.tab_calls() == [tab_url(3, "guitar-pro")]


def test_pro_beats_better_rated_tabs():
    ug, fetch = gmake(
        [pro(1, 3.0, 1), tabs(2, 5.0, 999)],
        {
            tab_url(1, "guitar-pro"): pro_page("D A D G B E"),
            tab_url(2, "tabs"): tab_page("E A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert tab_url(2, "tabs") not in fetch.calls


def test_pro_page_limit():
    results = [pro(i, 5.0 - i * 0.1) for i in range(1, 5)]
    pages = {tab_url(i, "guitar-pro"): pro_page("E A D G", "guitar") for i in range(1, 4)}
    pages[tab_url(4, "guitar-pro")] = pro_page("E A D G B E")
    ug, fetch = gmake(results, pages)
    assert MAX_PAGES_PER_TYPE == 3
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == [tab_url(i, "guitar-pro") for i in (1, 2, 3)]


def test_pro_fetch_error_skips_page():
    ug, _ = gmake(
        [pro(1, 4.9), pro(2, 4.0)],
        {
            tab_url(1, "guitar-pro"): FetchError("boom"),
            tab_url(2, "guitar-pro"): pro_page("D A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2, "guitar-pro")


# ------------------------------------------------------------------ plain Tabs


def test_tabs_used_when_no_pro_results():
    ug, _ = gmake([tabs(1)], {tab_url(1, "tabs"): tab_page("D A D G B E")})
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert m.tuning == T("D A D G B E", "guitar")
    assert m.url == tab_url(1, "tabs")


def test_tabs_ranked_by_rating_then_votes():
    ug, fetch = gmake(
        [tabs(1, 4.0, 500), tabs(2, 4.8, 3), tabs(3, 4.8, 9)],
        {
            tab_url(1, "tabs"): tab_page("E A D G B E"),
            tab_url(2, "tabs"): tab_page("D A D G B E"),
            tab_url(3, "tabs"): tab_page("D G D G B D"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.tuning.name == "Open G"
    assert fetch.tab_calls() == [tab_url(3, "tabs")]


def test_tabs_page_limit():
    results = [tabs(i, 5.0 - i * 0.1) for i in range(1, 5)]
    no_tuning = ug_tab_page(None, "guitar", 1, with_tuning=False)
    pages = {tab_url(i, "tabs"): no_tuning for i in range(1, 4)}
    pages[tab_url(4, "tabs")] = tab_page()
    ug, fetch = gmake(results, pages)
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == [tab_url(i, "tabs") for i in (1, 2, 3)]


def test_tabs_missing_and_invalid_tunings_skipped():
    ug, fetch = gmake(
        [tabs(1, 4.9), tabs(2, 4.8), tabs(3, 4.7)],
        {
            tab_url(1, "tabs"): ug_tab_page(None, "guitar", 1, with_tuning=False),
            tab_url(2, "tabs"): tab_page("not a tuning"),
            tab_url(3, "tabs"): tab_page("D A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(3, "tabs")
    assert fetch.tab_calls() == [tab_url(i, "tabs") for i in (1, 2, 3)]


def test_tabs_with_bass_shaped_tuning_skipped():
    ug, fetch = gmake(
        [tabs(1, 4.9), tabs(2, 4.8)],
        {tab_url(1, "tabs"): tab_page("E A D G"), tab_url(2, "tabs"): tab_page("D A D G B E")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2, "tabs")
    assert m.tuning == T("D A D G B E", "guitar")
    assert fetch.tab_calls() == [tab_url(1, "tabs"), tab_url(2, "tabs")]


def test_tab_page_without_store_skipped():
    ug, _ = gmake(
        [tabs(1, 4.9), tabs(2, 4.0)],
        {tab_url(1, "tabs"): "<html></html>", tab_url(2, "tabs"): tab_page("D A D G B E")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2, "tabs")


def test_seven_string_tab():
    ug, _ = gmake([tabs(1)], {tab_url(1, "tabs"): tab_page("B E A D G B E")})
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.tuning.string_count == 7
    assert m.tuning.name == "B Standard"


# --------------------------------------------------------------- ignored types


def test_other_types_ignored_in_guitar_mode():
    results = [
        ug_result(None, None, 4.9, 1000),
        ug_result(11, "Official", 5.0, 1000),
        ug_result(13, "Power", 5.0, 1000),
        ug_result(14, "Drum Tabs", 5.0, 1000),
        bass(15, 5.0, 1000),
    ]
    ug, fetch = gmake(results, {tab_url(15, "bass"): tab_page()})
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


def test_guitar_tabs_ignored_in_bass_mode():
    fetch = FakeFetch(
        {tab_url(1, "tabs"): tab_page("D A D G B E")}, SEARCH_URL, ug_search_page([tabs(1)])
    )
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


# ------------------------------------------------------------ exact / similar


def test_exact_preferred_over_similar_in_guitar_mode():
    ug, fetch = gmake(
        [pro(1, 5.0, 999, title="Schism (Live)"), tabs(2, 3.0, 1)],
        {
            tab_url(1, "guitar-pro"): pro_page("C G C F A D"),
            tab_url(2, "tabs"): tab_page("D A D G B E"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is True
    assert m.source == "ug-tab"
    assert tab_url(1, "guitar-pro") not in fetch.calls


def test_similar_used_when_no_exact():
    ug, _ = gmake(
        [tabs(1, title="Schism (Live)")], {tab_url(1, "tabs"): tab_page("D A D G B E")}
    )
    m = ug.lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is False
    assert m.matched_title == "Schism (Live)"


def test_other_artist_ignored():
    ug, fetch = gmake([tabs(1, artist="Opeth")], {tab_url(1, "tabs"): tab_page()})
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


def test_failures_return_none():
    for response in (FetchError("down"), "<html></html>", store_page({"x": 1})):
        fetch = FakeFetch({}, SEARCH_URL, response)
        assert UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism") is None


# --------------------------------------------------------------------- paging


class PagedFetch:
    def __init__(
        self, search_pages: Dict[int, Any], tabs_: Optional[Dict[str, Any]] = None
    ) -> None:
        self.search_pages = search_pages
        self.tabs = tabs_ or {}
        self.search_page_requests: List[int] = []

    def __call__(self, url: str) -> str:
        if url.startswith(SEARCH_URL):
            q = parse_qs(urlparse(url).query)
            page = int(q.get("page", ["1"])[0])
            self.search_page_requests.append(page)
            value = self.search_pages.get(page, FetchError("no such page"))
        else:
            value = self.tabs.get(url, FetchError("unknown"))
        if isinstance(value, Exception):
            raise value
        return str(value)


def paged(results, total=None, current=1):
    data: Dict[str, Any] = {"results": results}
    if total is not None:
        data["pagination"] = {"total": total, "current": current}
    return store_page(data)


def test_guitar_paging_continues_until_tabs_results_found():
    fetch = PagedFetch(
        {1: paged([pro(1), bass(9)], total=3), 2: paged([tabs(2)], total=3, current=2)},
        {
            tab_url(1, "guitar-pro"): pro_page("E A D G", "guitar"),
            tab_url(2, "tabs"): tab_page("D A D G B E"),
        },
    )
    m = UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert m.url == tab_url(2, "tabs")
    assert fetch.search_page_requests == [1, 2]


def test_guitar_paging_stops_when_tabs_results_on_page_one():
    fetch = PagedFetch(
        {1: paged([tabs(1)], total=5), 2: paged([tabs(2)], total=5, current=2)},
        {tab_url(1, "tabs"): tab_page("D A D G B E")},
    )
    UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert fetch.search_page_requests == [1]


def test_guitar_paging_ignores_tabs_of_other_songs():
    fetch = PagedFetch(
        {
            1: paged([tabs(9, artist="Opeth", title="Deliverance")], total=3),
            2: paged([tabs(2)], total=3, current=2),
        },
        {tab_url(2, "tabs"): tab_page("D A D G B E")},
    )
    m = UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2, "tabs")
    assert fetch.search_page_requests == [1, 2]


def test_bass_paging_still_waits_for_bass_tabs_even_with_guitar_tabs_on_page_one():
    fetch = PagedFetch(
        {1: paged([tabs(1)], total=3), 2: paged([bass(2)], total=3, current=2)},
        {tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch, "bass").lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert fetch.search_page_requests == [1, 2]


def test_guitar_paging_stops_at_max_pages():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=10),
            2: paged([pro(2)], total=10, current=2),
            3: paged([pro(3)], total=10, current=3),
            4: paged([tabs(4)], total=10, current=4),
        },
        {tab_url(4, "tabs"): tab_page()},
    )
    assert UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism") is None
    assert fetch.search_page_requests == [1, 2, 3]
