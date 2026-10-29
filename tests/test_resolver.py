from __future__ import annotations

from conftest import FakeSource, T, make_match

from bass_sort.cache import Entry
from bass_sort.resolver import resolve


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
