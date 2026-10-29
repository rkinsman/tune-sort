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

from bass_sort.sources import FetchError
from bass_sort.sources.ultimate_guitar import (
    MAX_PAGES_PER_TYPE,
    MAX_SEARCH_PAGES,
    SEARCH_URL,
    UltimateGuitar,
    parse_store,
    search_url,
)


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


def make(results, pages=None):
    fetch = FakeFetch(pages, SEARCH_URL, ug_search_page(results))
    return UltimateGuitar(fetch), fetch


def test_search_url():
    url = search_url("Tool", "Schism")
    assert url.startswith(SEARCH_URL)
    q = parse_qs(urlparse(url).query)
    assert q["search_type"] == ["title"]
    assert q["value"] == ["Tool Schism"]


def test_max_pages_constant():
    assert MAX_PAGES_PER_TYPE == 3


def test_parse_store_real_fixture():
    data = parse_store(fixture_text("ug/search_tool_schism.html"))
    results = data["store"]["page"]["data"]["results"]
    assert isinstance(results, list)
    assert any(r["id"] == 127745 for r in results)


def test_parse_store_tab_page():
    data = parse_store(fixture_text("ug/bass_127745.html"))
    assert data["store"]["page"]["data"]["tab_view"]["meta"]["tuning"]["value"] == "D A D G"


def test_real_fixtures_give_bass_tab_not_multi_instrument_pro():
    fetch = FakeFetch(
        {
            "https://tabs.ultimate-guitar.com/tab/tool/schism-guitar-pro-554368": fixture_text(
                "ug/pro_554368.html"
            ),
            "https://tabs.ultimate-guitar.com/tab/tool/schism-bass-127745": fixture_text(
                "ug/bass_127745.html"
            ),
        },
        SEARCH_URL,
        fixture_text("ug/search_tool_schism.html"),
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")
    assert m.tuning.name == "Drop D"
    assert m.url == "https://tabs.ultimate-guitar.com/tab/tool/schism-bass-127745"
    assert m.matched_artist == "Tool"
    assert m.matched_title == "Schism"
    assert m.exact is True
    # The best-rated Pro tab is tried first; nothing but Pro / Bass Tabs pages are fetched.
    tabs = fetch.tab_calls()
    assert tabs[0] == "https://tabs.ultimate-guitar.com/tab/tool/schism-guitar-pro-554368"
    for url in tabs:
        assert "guitar-pro" in url or "-bass-" in url
    assert len([u for u in tabs if "guitar-pro" in u]) <= 3


def test_bass_only_pro_tab_is_used_first():
    url = tab_url(1, "guitar-pro")
    ug, fetch = make(
        [pro(1), bass(2, 5.0, 500)],
        {url: ug_tab_page("E A D G", "bass", 1), tab_url(2): ug_tab_page("D A D G")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m.source == "ug-pro"
    assert m.tuning == T("E A D G")
    assert m.url == url
    assert tab_url(2) not in fetch.calls


def test_pro_instruments_case_insensitive():
    ug, _ = make([pro(1)], {tab_url(1, "guitar-pro"): ug_tab_page("D A D G", "Electric BASS", 1)})
    assert ug.lookup("Tool", "Schism").source == "ug-pro"


def test_pro_with_multiple_instruments_is_skipped():
    ug, _ = make(
        [pro(1), bass(2)],
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 2),
            tab_url(2): ug_tab_page("D A D G"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")


def test_pro_single_instrument_not_bass_is_skipped():
    ug, _ = make(
        [pro(1), bass(2)],
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G B E", "lead guitar", 1),
            tab_url(2): ug_tab_page("D A D G"),
        },
    )
    assert ug.lookup("Tool", "Schism").source == "ug-bass"


def test_pro_ranked_by_rating_then_votes():
    ug, fetch = make(
        [pro(1, 4.0, 5), pro(2, 4.9, 5), pro(3, 4.9, 50)],
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G"),
            tab_url(2, "guitar-pro"): ug_tab_page("D A D G"),
            tab_url(3, "guitar-pro"): ug_tab_page("C G C F"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m.tuning == T("C G C F")
    assert fetch.tab_calls() == [tab_url(3, "guitar-pro")]


def test_bass_ranked_by_rating_then_votes():
    ug, fetch = make(
        [bass(1, 4.0, 500), bass(2, 4.8, 3), bass(3, 4.8, 9)],
        {
            tab_url(1): ug_tab_page("E A D G"),
            tab_url(2): ug_tab_page("D A D G"),
            tab_url(3): ug_tab_page("C G C F"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m.source == "ug-bass"
    assert m.tuning == T("C G C F")
    assert fetch.tab_calls() == [tab_url(3)]


def test_pro_page_limit_and_order():
    results = [pro(i, 5.0 - i * 0.1) for i in range(1, 5)]
    pages = {tab_url(i, "guitar-pro"): ug_tab_page("E A D G", "guitar", 1) for i in range(1, 4)}
    pages[tab_url(4, "guitar-pro")] = ug_tab_page("E A D G", "bass", 1)
    ug, fetch = make(results, pages)
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == [tab_url(i, "guitar-pro") for i in (1, 2, 3)]


def test_bass_page_limit():
    results = [bass(i, 5.0 - i * 0.1) for i in range(1, 5)]
    pages = {tab_url(i): ug_tab_page(None, with_tuning=False) for i in range(1, 4)}
    pages[tab_url(4)] = ug_tab_page("E A D G")
    ug, fetch = make(results, pages)
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == [tab_url(i) for i in (1, 2, 3)]


def test_fetch_error_on_tab_page_skips_it():
    ug, _ = make(
        [bass(1, 4.9), bass(2, 4.0)],
        {tab_url(1): FetchError("boom"), tab_url(2): ug_tab_page("D A D G")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m.url == tab_url(2)


def test_missing_and_invalid_tuning_skipped():
    ug, _ = make(
        [bass(1, 4.9), bass(2, 4.8), bass(3, 4.0)],
        {
            tab_url(1): ug_tab_page(with_tuning=False),
            tab_url(2): ug_tab_page("not a tuning"),
            tab_url(3): ug_tab_page("D A D G"),
        },
    )
    assert ug.lookup("Tool", "Schism").url == tab_url(3)


def test_tab_page_without_store_skipped():
    ug, _ = make(
        [bass(1, 4.9), bass(2, 4.0)],
        {tab_url(1): "<html><body>nothing</body></html>", tab_url(2): ug_tab_page("D A D G")},
    )
    assert ug.lookup("Tool", "Schism").url == tab_url(2)


def test_five_string_bass_tab():
    ug, _ = make([bass(1)], {tab_url(1): ug_tab_page("B E A D G")})
    m = ug.lookup("Tool", "Schism")
    assert m.tuning.string_count == 5
    assert m.tuning.name == "B Standard"


def test_ignored_types_and_marketing_entries():
    results = [
        ug_result(None, None, 4.9, 1000),
        ug_result(11, "Official", 5.0, 1000),
        ug_result(12, "Tabs", 5.0, 1000),
        ug_result(13, "Power", 5.0, 1000),
        ug_result(14, "Drum Tabs", 5.0, 1000),
    ]
    ug, fetch = make(results)
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


def test_no_matches_returns_none():
    ug, _ = make([])
    assert ug.lookup("Tool", "Schism") is None


def test_other_artist_or_title_results_ignored():
    results = [
        bass(1, artist="Opeth"),
        bass(2, title="Parabola"),
    ]
    ug, fetch = make(results, {tab_url(1): ug_tab_page(), tab_url(2): ug_tab_page()})
    assert ug.lookup("Tool", "Schism") is None
    assert fetch.tab_calls() == []


def test_exact_preferred_over_better_rated_similar():
    similar = bass(1, 5.0, 999, title="Schism (Live)")
    exact = bass(2, 3.0, 1)
    ug, fetch = make(
        [similar, exact],
        {tab_url(1): ug_tab_page("C G C F"), tab_url(2): ug_tab_page("D A D G")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m.exact is True
    assert m.url == tab_url(2)
    assert tab_url(1) not in fetch.calls


def test_exact_bass_beats_similar_pro():
    similar_pro = pro(1, title="Schism (Live)")
    ug, _ = make(
        [similar_pro, bass(2)],
        {
            tab_url(1, "guitar-pro"): ug_tab_page("C G C F", "bass", 1),
            tab_url(2): ug_tab_page("D A D G"),
        },
    )
    m = ug.lookup("Tool", "Schism")
    assert m.source == "ug-bass"
    assert m.exact is True


def test_similar_used_when_no_exact_results():
    ug, _ = make([bass(1, title="Schism (Live)")], {tab_url(1): ug_tab_page("D A D G")})
    m = ug.lookup("Tool", "Schism")
    assert m.exact is False
    assert m.matched_title == "Schism (Live)"
    assert m.matched_artist == "Tool"
    assert m.tuning == T("D A D G")


def test_similar_used_when_exact_results_unusable():
    ug, _ = make(
        [bass(1), bass(2, title="Schism (Live)")],
        {tab_url(1): ug_tab_page(with_tuning=False), tab_url(2): ug_tab_page("D A D G")},
    )
    m = ug.lookup("Tool", "Schism")
    assert m.exact is False
    assert m.url == tab_url(2)


def test_search_fetch_error_returns_none():
    fetch = FakeFetch({}, SEARCH_URL, FetchError("down"))
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None


def test_search_page_without_store_returns_none():
    fetch = FakeFetch({}, SEARCH_URL, "<html><body>captcha</body></html>")
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None


def test_store_without_results_returns_none():
    fetch = FakeFetch({}, SEARCH_URL, store_page({"something": "else"}))
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None


# ------------------------------------------------------- search-result pagination


class PagedFetch:
    """Fake fetch that serves search pages by their `page` query param (default 1).

    `search_pages` maps page number -> html (or an Exception to raise). Pages not in the
    map raise FetchError. Other URLs come from `tabs`.
    """

    def __init__(
        self, search_pages: Dict[int, Any], tabs: Optional[Dict[str, Any]] = None
    ) -> None:
        self.search_pages = search_pages
        self.tabs = tabs or {}
        self.calls: List[str] = []
        self.search_page_requests: List[int] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        if url.startswith(SEARCH_URL):
            q = parse_qs(urlparse(url).query)
            page = int(q.get("page", ["1"])[0])
            self.search_page_requests.append(page)
            value = self.search_pages.get(page, FetchError("no such page"))
            if isinstance(value, Exception):
                raise value
            return str(value)
        value = self.tabs.get(url, FetchError("unknown url: " + url))
        if isinstance(value, Exception):
            raise value
        return str(value)

    def tab_calls(self) -> List[str]:
        return [c for c in self.calls if not c.startswith(SEARCH_URL)]


def paged(results, total=None, current=1):
    data: Dict[str, Any] = {"search_query": "q", "results": results}
    if total is not None:
        data["pagination"] = {"total": total, "current": current}
    return store_page(data)


def test_max_search_pages_constant():
    assert MAX_SEARCH_PAGES == 3


def test_search_url_page_param():
    first = search_url("Tool", "Schism")
    assert "page" not in parse_qs(urlparse(first).query)
    assert search_url("Tool", "Schism", 1) == first
    second = search_url("Tool", "Schism", 2)
    assert second.startswith(SEARCH_URL)
    q = parse_qs(urlparse(second).query)
    assert q["page"] == ["2"]
    assert q["search_type"] == ["title"]
    assert q["value"] == ["Tool Schism"]


def test_bass_tabs_on_page_two_are_found():
    fetch = PagedFetch(
        {
            1: paged([pro(1, 4.9)], total=3),
            2: paged([bass(2)], total=3, current=2),
        },
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G B E", "lead guitar", 1),
            tab_url(2): ug_tab_page("D A D G"),
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.tuning == T("D A D G")
    assert m.url == tab_url(2)
    assert fetch.search_page_requests == [1, 2]


def test_no_page_two_request_when_page_one_has_bass_tabs():
    fetch = PagedFetch(
        {1: paged([bass(1)], total=5), 2: paged([bass(2)], total=5, current=2)},
        {tab_url(1): ug_tab_page("D A D G"), tab_url(2): ug_tab_page("C G C F")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(1)
    assert fetch.search_page_requests == [1]


def test_similar_bass_tabs_on_page_one_stop_paging():
    fetch = PagedFetch(
        {1: paged([bass(1, title="Schism (Live)")], total=5)},
        {tab_url(1): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is False
    assert fetch.search_page_requests == [1]


def test_bass_tabs_of_another_song_do_not_stop_paging():
    fetch = PagedFetch(
        {
            1: paged([pro(1), bass(9, artist="Opeth", title="Deliverance")], total=3),
            2: paged([bass(2)], total=3, current=2),
        },
        {tab_url(2): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2)
    assert fetch.search_page_requests == [1, 2]


def test_good_pro_on_page_one_beats_bass_on_page_two():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=3),
            2: paged([bass(2, 5.0, 999)], total=3, current=2),
        },
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1),
            tab_url(2): ug_tab_page("D A D G"),
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.url == tab_url(1, "guitar-pro")
    # Paging continued until Bass Tabs results were found.
    assert fetch.search_page_requests == [1, 2]


def test_pages_gathered_across_three_pages():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=9),
            2: paged([pro(2)], total=9, current=2),
            3: paged([bass(3)], total=9, current=3),
        },
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G B E", "guitar", 1),
            tab_url(2, "guitar-pro"): ug_tab_page("E A D G B E", "guitar", 1),
            tab_url(3): ug_tab_page("D A D G"),
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(3)
    assert fetch.search_page_requests == [1, 2, 3]


def test_stops_after_max_search_pages():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=10),
            2: paged([pro(2)], total=10, current=2),
            3: paged([pro(3)], total=10, current=3),
            4: paged([bass(4)], total=10, current=4),
        },
        {tab_url(4): ug_tab_page("D A D G")},
    )
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
    assert fetch.search_page_requests == [1, 2, 3]


def test_stops_at_pagination_total():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=2),
            2: paged([pro(2)], total=2, current=2),
            3: paged([bass(3)], total=2, current=3),
        },
        {tab_url(3): ug_tab_page("D A D G")},
    )
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
    assert fetch.search_page_requests == [1, 2]


def test_single_page_total_means_no_second_request():
    fetch = PagedFetch({1: paged([pro(1)], total=1), 2: paged([bass(2)], total=1, current=2)})
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
    assert fetch.search_page_requests == [1]


def test_missing_pagination_stops_after_first_page():
    fetch = PagedFetch(
        {1: paged([pro(1)]), 2: paged([bass(2)])},
        {tab_url(2): ug_tab_page("D A D G")},
    )
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
    assert fetch.search_page_requests == [1]


def test_fetch_error_on_page_two_keeps_page_one_results():
    fetch = PagedFetch(
        {1: paged([pro(1)], total=3), 2: FetchError("down")},
        {tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1)},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert fetch.search_page_requests == [1, 2]


def test_unparseable_page_two_keeps_page_one_results():
    fetch = PagedFetch(
        {1: paged([pro(1)], total=3), 2: "<html>captcha</html>", 3: paged([bass(3)], 3, 3)},
        {
            tab_url(1, "guitar-pro"): ug_tab_page("E A D G", "bass", 1),
            tab_url(3): ug_tab_page("C G C F"),
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    # Paging stops at the bad page; page 3 is never requested.
    assert fetch.search_page_requests == [1, 2]


def test_failed_page_two_with_nothing_usable_returns_none():
    fetch = PagedFetch({1: paged([pro(1)], total=3), 2: FetchError("down")})
    assert UltimateGuitar(fetch).lookup("Tool", "Schism") is None
