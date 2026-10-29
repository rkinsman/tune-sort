from __future__ import annotations

import dataclasses

from tests.conftest import FakeSource, T, make_match
from tune_sort.cache import Entry
from tune_sort.resolver import resolve


def test_cache_hit_asks_no_source(cache):
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    s = FakeSource("a", default=make_match("E A D G"))
    r = resolve("Tool", "Schism", [s], cache)
    assert s.calls == []
    assert r.source == "cache"
    assert r.tuning == T("D A D G")
    assert r.needs_review is False
    assert (r.artist, r.title) == ("Tool", "Schism")


def test_cache_hit_unconfirmed_entry(cache):
    cache.put("Tool", "Schism", Entry(T("D A D G"), "ug-bass", False))
    s = FakeSource("a", default=make_match("E A D G"))
    assert resolve("Tool", "Schism", [s], cache).source == "cache"
    assert s.calls == []


def test_every_source_is_asked_even_after_an_exact_match(cache):
    a = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    b = FakeSource("b", default=make_match("D A D G", "songsterr"))
    resolve("Tool", "Schism", [a, b], cache)
    assert a.calls == [("Tool", "Schism")]
    assert b.calls == [("Tool", "Schism")]


def test_agreeing_exact_matches_accept_primary(cache):
    a = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    b = FakeSource("b", default=make_match("D A D G", "songsterr"))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.tuning == T("D A D G")
    assert r.source == "ug-bass"
    assert r.needs_review is False
    assert cache.get("Tool", "Schism") == Entry(T("D A D G"), "ug-bass", False)
    assert cache.review_items() == []


def test_enharmonic_spellings_agree(cache):
    a = FakeSource("a", default=make_match("D# G# C# F#", "ug-bass"))
    b = FakeSource("b", default=make_match("Eb Ab Db Gb", "songsterr"))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.needs_review is False
    assert r.source == "ug-bass"
    assert cache.review_items() == []


def test_disagreeing_exact_matches_need_review(cache):
    m1 = make_match("E A D G", "ug-bass")
    m2 = make_match("D G C F", "songsterr")
    a = FakeSource("a", default=m1)
    b = FakeSource("b", default=m2)
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.tuning is None
    assert r.source is None
    assert r.needs_review is True
    assert r.candidates == (m1, m2)
    assert cache.get("Tool", "Schism") is None
    items = cache.review_items()
    assert len(items) == 1
    assert (items[0].artist, items[0].title) == ("Tool", "Schism")
    assert items[0].candidates == (m1, m2)


def test_four_and_five_string_disagree(cache):
    m1 = make_match("B E A D", "ug-bass")
    m2 = make_match("B E A D G", "songsterr")
    r = resolve("Tool", "Schism", [FakeSource("a", default=m1), FakeSource("b", default=m2)], cache)
    assert r.needs_review is True
    assert r.candidates == (m1, m2)
    assert cache.get("Tool", "Schism") is None


def test_disagreement_candidates_exact_first_then_non_exact(cache):
    fuzzy = make_match("C G C F", "ug-pro", exact=False, title="Schism (Live)")
    e1 = make_match("E A D G", "ug-bass")
    e2 = make_match("D G C F", "songsterr")
    fuzzy2 = make_match("A D G C", "other", exact=False, title="Schism (Demo)")
    sources = [
        FakeSource("a", default=fuzzy),
        FakeSource("b", default=e1),
        FakeSource("c", default=e2),
        FakeSource("d", default=fuzzy2),
    ]
    r = resolve("Tool", "Schism", sources, cache)
    assert r.needs_review is True
    assert r.candidates == (e1, e2, fuzzy, fuzzy2)
    assert cache.review_items()[0].candidates == (e1, e2, fuzzy, fuzzy2)


def test_primary_is_first_exact_in_source_order_for_disagreement_order(cache):
    e1 = make_match("D G C F", "songsterr")
    e2 = make_match("E A D G", "ug-bass")
    r = resolve("Tool", "Schism", [FakeSource("a", default=e1), FakeSource("b", default=e2)], cache)
    assert r.candidates == (e1, e2)


def test_non_exact_other_source_never_disagrees(cache):
    a = FakeSource("a", default=make_match("E A D G", "ug-bass"))
    b = FakeSource("b", default=make_match("D G C F", "songsterr", exact=False))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.needs_review is False
    assert r.tuning == T("E A D G")
    assert r.source == "ug-bass"
    assert cache.get("Tool", "Schism") == Entry(T("E A D G"), "ug-bass", False)
    assert cache.review_items() == []


def test_first_source_empty_second_exact_accepted(cache):
    a = FakeSource("a", default=None)
    b = FakeSource("b", default=make_match("D G C F", "songsterr"))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert a.calls == [("Tool", "Schism")]
    assert r.source == "songsterr"
    assert r.tuning == T("D G C F")
    assert cache.get("Tool", "Schism") == Entry(T("D G C F"), "songsterr", False)


def test_non_exact_then_exact_uses_exact(cache):
    a = FakeSource("a", default=make_match("C G C F", "ug-bass", exact=False))
    b = FakeSource("b", default=make_match("E A D G", "songsterr"))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.source == "songsterr"
    assert r.tuning == T("E A D G")
    assert cache.review_items() == []


def test_single_source_exact_accepted(cache):
    a = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [a], cache)
    assert r.needs_review is False
    assert r.source == "ug-bass"
    assert cache.get("Tool", "Schism") == Entry(T("D A D G"), "ug-bass", False)


def test_no_exact_goes_to_review_with_all_candidates(cache):
    m1 = make_match("C G C F", "ug-bass", exact=False, title="Schism (Live)")
    m2 = make_match("E A D G", "songsterr", exact=False, title="Schism (Demo)")
    a = FakeSource("a", default=m1)
    b = FakeSource("b", default=m2)
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.tuning is None
    assert r.source is None
    assert r.needs_review is True
    assert r.candidates == (m1, m2)
    assert cache.get("Tool", "Schism") is None
    items = cache.review_items()
    assert len(items) == 1
    assert (items[0].artist, items[0].title) == ("Tool", "Schism")
    assert items[0].candidates == (m1, m2)


def test_no_matches_at_all_needs_review(cache):
    a = FakeSource("a")
    r = resolve("Tool", "Schism", [a], cache)
    assert r.needs_review is True
    assert r.tuning is None
    assert r.candidates == ()
    assert cache.get("Tool", "Schism") is None
    assert [(i.artist, i.title) for i in cache.review_items()] == [("Tool", "Schism")]


def test_no_sources_needs_review(cache):
    assert resolve("Tool", "Schism", [], cache).needs_review is True


# --------------------------------------------- second round with the part name

ARTIST = "TesseracT"
FULL = "Of Matter - Retrospect"
PART = "Retrospect"
A_STD_5 = "A D G C F"


def _with_url(match, url):
    return dataclasses.replace(match, url=url)


def test_part_name_round_accepts_agreeing_exact_matches(cache):
    ug = FakeSource(
        "ug",
        {
            (ARTIST, FULL): None,
            (ARTIST, PART): make_match(A_STD_5, "ug-bass", True, ARTIST, PART),
        },
    )
    sg = FakeSource(
        "songsterr",
        {
            (ARTIST, FULL): make_match(A_STD_5, "songsterr", False, ARTIST, PART),
            (ARTIST, PART): make_match(A_STD_5, "songsterr", True, ARTIST, PART),
        },
    )
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.needs_review is False
    assert r.source == "ug-bass"
    assert r.tuning == T(A_STD_5)
    assert r.tuning.string_count == 5
    assert (r.artist, r.title) == (ARTIST, FULL)
    assert cache.get(ARTIST, FULL) == Entry(T(A_STD_5), "ug-bass", False)
    assert cache.review_items() == []
    assert ug.calls == [(ARTIST, FULL), (ARTIST, PART)]
    assert sg.calls == [(ARTIST, FULL), (ARTIST, PART)]


def test_part_name_round_disagreement_goes_to_review(cache):
    ug_exact = make_match(A_STD_5, "ug-bass", True, ARTIST, PART)
    sg_exact = make_match("B E A D G", "songsterr", True, ARTIST, PART)
    ug_fuzzy1 = _with_url(
        make_match("C G C F", "ug-pro", False, ARTIST, "Of Matter"), "https://example.test/ug-f1"
    )
    # Same (source, url) as the second-round exact songsterr match: must be dropped.
    sg_fuzzy1 = make_match("B E A D G", "songsterr", False, ARTIST, PART)
    ug = FakeSource("ug", {(ARTIST, FULL): ug_fuzzy1, (ARTIST, PART): ug_exact})
    sg = FakeSource("songsterr", {(ARTIST, FULL): sg_fuzzy1, (ARTIST, PART): sg_exact})
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.needs_review is True
    assert r.tuning is None
    assert r.source is None
    assert r.candidates == (ug_exact, sg_exact, ug_fuzzy1)
    assert cache.get(ARTIST, FULL) is None
    items = cache.review_items()
    assert len(items) == 1
    assert (items[0].artist, items[0].title) == (ARTIST, FULL)
    assert items[0].candidates == (ug_exact, sg_exact, ug_fuzzy1)


def test_no_second_round_when_first_round_has_exact(cache):
    ug = FakeSource("ug", {(ARTIST, FULL): make_match(A_STD_5, "ug-bass", True, ARTIST, FULL)})
    sg = FakeSource("songsterr")
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.source == "ug-bass"
    assert ug.calls == [(ARTIST, FULL)]
    assert sg.calls == [(ARTIST, FULL)]


def test_no_second_round_without_part_title(cache):
    ug = FakeSource("ug")
    sg = FakeSource("songsterr")
    r = resolve("Tool", "Schism", [ug, sg], cache)
    assert r.needs_review is True
    assert ug.calls == [("Tool", "Schism")]
    assert sg.calls == [("Tool", "Schism")]


def test_no_second_round_for_version_suffix(cache):
    ug = FakeSource("ug")
    r = resolve("Tool", "Song - Live", [ug], cache)
    assert r.needs_review is True
    assert ug.calls == [("Tool", "Song - Live")]


def test_both_rounds_fuzzy_keeps_deduplicated_candidates(cache):
    u1 = _with_url(make_match("E A D G", "ug-bass", False, ARTIST, "Of Matter"), "https://x/u1")
    s1 = _with_url(make_match("D G C F", "songsterr", False, ARTIST, PART), "https://x/s1")
    u2 = _with_url(make_match("A D G C", "ug-bass", False, ARTIST, "Retrospect (Live)"), "https://x/u2")
    s1_again = _with_url(make_match("D G C F", "songsterr", False, ARTIST, PART), "https://x/s1")
    ug = FakeSource("ug", {(ARTIST, FULL): u1, (ARTIST, PART): u2})
    sg = FakeSource("songsterr", {(ARTIST, FULL): s1, (ARTIST, PART): s1_again})
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.needs_review is True
    assert r.tuning is None
    assert len(r.candidates) == 3
    assert {(c.source, c.url) for c in r.candidates} == {
        ("ug-bass", "https://x/u1"),
        ("songsterr", "https://x/s1"),
        ("ug-bass", "https://x/u2"),
    }
    assert all(c.exact is False for c in r.candidates)
    assert cache.get(ARTIST, FULL) is None
    items = cache.review_items()
    assert [(i.artist, i.title) for i in items] == [(ARTIST, FULL)]
    assert len(items[0].candidates) == 3
    assert ug.calls == [(ARTIST, FULL), (ARTIST, PART)]
    assert sg.calls == [(ARTIST, FULL), (ARTIST, PART)]


def test_second_round_with_nothing_found_needs_review(cache):
    ug = FakeSource("ug")
    r = resolve(ARTIST, FULL, [ug], cache)
    assert r.needs_review is True
    assert r.candidates == ()
    assert ug.calls == [(ARTIST, FULL), (ARTIST, PART)]
