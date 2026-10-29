"""UG search paging stops early only once every used tab type has an EXACT result."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from conftest import T, store_page, ug_result, ug_tab_page

from tune_sort.sources import FetchError
from tune_sort.sources.ultimate_guitar import SEARCH_URL, UltimateGuitar


def tab_url(id, kind):
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
        self.tab_requests: List[str] = []

    def __call__(self, url: str) -> str:
        if url.startswith(SEARCH_URL):
            page = int(parse_qs(urlparse(url).query).get("page", ["1"])[0])
            self.search_page_requests.append(page)
            value = self.search_pages.get(page, FetchError("no such page"))
        else:
            self.tab_requests.append(url)
            value = self.tab_pages.get(url, FetchError("unknown url: " + url))
        if isinstance(value, Exception):
            raise value
        return str(value)


def paged(results, total=None, current=1):
    data: Dict[str, Any] = {"search_query": "q", "results": results}
    if total is not None:
        data["pagination"] = {"total": total, "current": current}
    return store_page(data)


BASS_ONLY_PRO = ug_tab_page("E A D G", "bass", 1)
GUITAR_PRO = ug_tab_page("E A D G B E", "lead guitar", 1)
GUITAR_TAB = ug_tab_page("D A D G B E", "guitar", 1)


# ------------------------------------------------------------- similar never stops


def test_similar_tab_on_page_one_exact_on_page_two_is_used():
    fetch = PagedFetch(
        {
            1: paged([bass(1, 5.0, 999, title="Schism (Live)")], total=3),
            2: paged([bass(2, 3.0, 1)], total=3, current=2),
        },
        {tab_url(1, "bass"): ug_tab_page("C G C F"), tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is True
    assert m.url == tab_url(2, "bass")
    assert m.tuning == T("D A D G")
    assert m.source == "ug-bass"
    assert fetch.search_page_requests == [1, 2]
    assert tab_url(1, "bass") not in fetch.tab_requests


def test_similar_tab_on_page_one_exact_on_page_two_default_kinds():
    # No exact Pro tab exists, so default kinds keep paging through page 3.
    fetch = PagedFetch(
        {
            1: paged([bass(1, title="Schism (Live)")], total=3),
            2: paged([bass(2)], total=3, current=2),
            3: paged([], total=3, current=3),
        },
        {tab_url(1, "bass"): ug_tab_page("C G C F"), tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is True
    assert m.url == tab_url(2, "bass")
    assert fetch.search_page_requests == [1, 2, 3]


def test_only_similar_results_page_through_to_the_limit_then_use_similar():
    fetch = PagedFetch(
        {
            1: paged([bass(1, title="Schism (Live)")], total=9),
            2: paged([bass(2, title="Schism (Demo)")], total=9, current=2),
            3: paged([bass(3, 4.5, title="Schism (Acoustic)")], total=9, current=3),
            4: paged([bass(4)], total=9, current=4),
        },
        {
            tab_url(1, "bass"): ug_tab_page("D A D G"),
            tab_url(2, "bass"): ug_tab_page("D A D G"),
            tab_url(3, "bass"): ug_tab_page("D A D G"),
        },
    )
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is False
    assert fetch.search_page_requests == [1, 2, 3]


def test_similar_pro_does_not_count_for_default_kinds():
    fetch = PagedFetch(
        {
            1: paged([pro(1, title="Schism (Live)"), bass(2)], total=3),
            2: paged([pro(3)], total=3, current=2),
        },
        {
            tab_url(2, "bass"): ug_tab_page("D A D G"),
            tab_url(3, "guitar-pro"): BASS_ONLY_PRO,
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.url == tab_url(3, "guitar-pro")
    assert fetch.search_page_requests == [1, 2]


# -------------------------------------------------------------- ug-pro (kinds=pro)


def test_pro_kind_ignores_exact_bass_tab_for_stopping_and_finds_page_two_pro():
    fetch = PagedFetch(
        {
            1: paged([bass(1)], total=3),
            2: paged([pro(2)], total=3, current=2),
        },
        {
            tab_url(1, "bass"): ug_tab_page("D A D G"),
            tab_url(2, "guitar-pro"): BASS_ONLY_PRO,
        },
    )
    m = UltimateGuitar(fetch, "bass", ("pro",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.url == tab_url(2, "guitar-pro")
    assert m.tuning == T("E A D G")
    assert fetch.search_page_requests == [1, 2]
    assert tab_url(1, "bass") not in fetch.tab_requests


def test_pro_kind_stops_after_exact_pro_on_page_one():
    fetch = PagedFetch(
        {1: paged([pro(1)], total=5), 2: paged([pro(2)], total=5, current=2)},
        {tab_url(1, "guitar-pro"): BASS_ONLY_PRO},
    )
    m = UltimateGuitar(fetch, "bass", ("pro",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(1, "guitar-pro")
    assert fetch.search_page_requests == [1]


def test_pro_kind_similar_pro_does_not_stop_paging():
    fetch = PagedFetch(
        {
            1: paged([pro(1, title="Schism (Live)")], total=3),
            2: paged([pro(2)], total=3, current=2),
        },
        {
            tab_url(1, "guitar-pro"): ug_tab_page("C G C F", "bass", 1),
            tab_url(2, "guitar-pro"): BASS_ONLY_PRO,
        },
    )
    m = UltimateGuitar(fetch, "bass", ("pro",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.exact is True
    assert m.url == tab_url(2, "guitar-pro")
    assert fetch.search_page_requests == [1, 2]


# -------------------------------------------------------------- tab-only (kinds=tab)


def test_tab_kind_stops_after_exact_bass_tab_on_page_one():
    fetch = PagedFetch(
        {1: paged([bass(1)], total=5), 2: paged([bass(2)], total=5, current=2)},
        {tab_url(1, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(1, "bass")
    assert fetch.search_page_requests == [1]


def test_tab_kind_ignores_exact_pro_for_stopping():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=3),
            2: paged([bass(2)], total=3, current=2),
        },
        {tab_url(1, "guitar-pro"): BASS_ONLY_PRO, tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch, "bass", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-bass"
    assert m.url == tab_url(2, "bass")
    assert fetch.search_page_requests == [1, 2]
    assert tab_url(1, "guitar-pro") not in fetch.tab_requests


def test_guitar_tab_kind_stops_after_exact_tabs():
    fetch = PagedFetch(
        {1: paged([tabs(1)], total=5), 2: paged([tabs(2)], total=5, current=2)},
        {tab_url(1, "tabs"): GUITAR_TAB},
    )
    m = UltimateGuitar(fetch, "guitar", ("tab",)).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-tab"
    assert fetch.search_page_requests == [1]


# ----------------------------------------------------------------- default kinds


def test_default_kinds_stop_when_page_one_has_exact_pro_and_exact_bass():
    fetch = PagedFetch(
        {
            1: paged([pro(1), bass(2)], total=5),
            2: paged([bass(3)], total=5, current=2),
        },
        {tab_url(1, "guitar-pro"): BASS_ONLY_PRO, tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert fetch.search_page_requests == [1]


def test_default_kinds_continue_when_only_exact_bass_tab_on_page_one():
    fetch = PagedFetch(
        {
            1: paged([bass(1)], total=2),
            2: paged([pro(2)], total=2, current=2),
        },
        {tab_url(1, "bass"): ug_tab_page("D A D G"), tab_url(2, "guitar-pro"): BASS_ONLY_PRO},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert m.url == tab_url(2, "guitar-pro")
    assert fetch.search_page_requests == [1, 2]


def test_default_kinds_continue_when_only_exact_pro_on_page_one_and_bass_on_page_two():
    fetch = PagedFetch(
        {
            1: paged([pro(1)], total=2),
            2: paged([bass(2)], total=2, current=2),
        },
        {tab_url(1, "guitar-pro"): GUITAR_PRO, tab_url(2, "bass"): ug_tab_page("D A D G")},
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(2, "bass")
    assert fetch.search_page_requests == [1, 2]


def test_default_kinds_exact_results_of_other_songs_do_not_stop_paging():
    fetch = PagedFetch(
        {
            1: paged(
                [
                    pro(1, artist="Opeth", title="Deliverance"),
                    bass(2, artist="Opeth", title="Deliverance"),
                ],
                total=3,
            ),
            2: paged([pro(3), bass(4)], total=3, current=2),
        },
        {
            tab_url(3, "guitar-pro"): BASS_ONLY_PRO,
            tab_url(4, "bass"): ug_tab_page("D A D G"),
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(3, "guitar-pro")
    assert fetch.search_page_requests == [1, 2]


def test_exact_pro_and_exact_bass_split_across_three_pages():
    fetch = PagedFetch(
        {
            1: paged([bass(1, title="Schism (Live)")], total=9),
            2: paged([bass(2)], total=9, current=2),
            3: paged([pro(3)], total=9, current=3),
            4: paged([pro(4)], total=9, current=4),
        },
        {
            tab_url(2, "bass"): ug_tab_page("D A D G"),
            tab_url(3, "guitar-pro"): BASS_ONLY_PRO,
        },
    )
    m = UltimateGuitar(fetch).lookup("Tool", "Schism")
    assert m is not None
    assert m.url == tab_url(3, "guitar-pro")
    assert fetch.search_page_requests == [1, 2, 3]


# ------------------------------------------------------------------ guitar default


def test_guitar_default_kinds_stop_with_exact_pro_and_exact_tabs_on_page_one():
    fetch = PagedFetch(
        {
            1: paged([pro(1), tabs(2)], total=5),
            2: paged([tabs(3)], total=5, current=2),
        },
        {tab_url(1, "guitar-pro"): GUITAR_PRO, tab_url(2, "tabs"): GUITAR_TAB},
    )
    m = UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert fetch.search_page_requests == [1]


def test_guitar_default_kinds_continue_with_only_exact_tabs_on_page_one():
    fetch = PagedFetch(
        {
            1: paged([tabs(1)], total=2),
            2: paged([pro(2)], total=2, current=2),
        },
        {
            tab_url(1, "tabs"): ug_tab_page("E A D G B E", "guitar", 1),
            tab_url(2, "guitar-pro"): GUITAR_PRO,
        },
    )
    m = UltimateGuitar(fetch, "guitar").lookup("Tool", "Schism")
    assert m is not None
    assert m.source == "ug-pro"
    assert fetch.search_page_requests == [1, 2]
