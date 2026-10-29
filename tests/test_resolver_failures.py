"""Resolver: lookup failures, already-queued songs and `recheck`."""
from __future__ import annotations

from conftest import FakeSource, T, failing_source, make_match

from tune_sort.cache import Entry
from tune_sort.resolver import Resolution, resolve
from tune_sort.sources import SourceError

ARTIST = "TesseracT"
FULL = "Of Matter - Retrospect"
PART = "Retrospect"


# ------------------------------------------------------------ Resolution properties


def test_resolution_defaults_and_properties():
    r = Resolution("Tool", "Schism", None, None)
    assert r.candidates == ()
    assert r.failed == ()
    assert r.needs_review is True
    assert r.lookup_failed is False


def test_resolution_failed_is_not_review():
    r = Resolution("Tool", "Schism", None, None, (), ("ug",))
    assert r.needs_review is False
    assert r.lookup_failed is True


def test_resolution_with_tuning_is_neither():
    r = Resolution("Tool", "Schism", T("D A D G"), "ug-bass")
    assert r.needs_review is False
    assert r.lookup_failed is False


# ------------------------------------------------------------------ failing sources


def test_single_failing_source_is_a_lookup_failure(cache):
    a = failing_source("a")
    r = resolve("Tool", "Schism", [a], cache)
    assert r.tuning is None
    assert r.source is None
    assert r.candidates == ()
    assert r.failed == ("a",)
    assert r.lookup_failed is True
    assert r.needs_review is False
    assert (r.artist, r.title) == ("Tool", "Schism")


def test_lookup_failure_caches_nothing_and_queues_nothing(cache):
    resolve("Tool", "Schism", [failing_source("a")], cache)
    assert cache.get("Tool", "Schism") is None
    assert cache.review_items() == []


def test_lookup_failure_is_retried_on_next_resolve(cache):
    a = failing_source("a")
    resolve("Tool", "Schism", [a], cache)
    resolve("Tool", "Schism", [a], cache)
    assert a.calls[0] == ("Tool", "Schism")
    assert a.calls.count(("Tool", "Schism")) >= 2


def test_lookup_failure_then_success_is_accepted(cache):
    resolve("Tool", "Schism", [failing_source("a")], cache)
    ok = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [ok], cache)
    assert r.tuning == T("D A D G")
    assert r.failed == ()
    assert cache.get("Tool", "Schism") == Entry(T("D A D G"), "ug-bass", False)


def test_other_sources_still_asked_when_one_fails(cache):
    a = failing_source("a")
    b = FakeSource("b", default=make_match("D A D G", "songsterr"))
    c = FakeSource("c")
    r = resolve("Tool", "Schism", [a, b, c], cache)
    assert a.calls == [("Tool", "Schism")]
    assert b.calls == [("Tool", "Schism")]
    assert c.calls == [("Tool", "Schism")]
    assert r.failed == ("a",)


def test_failure_with_an_exact_match_from_another_source_caches_nothing(cache):
    a = failing_source("a")
    b = FakeSource("b", default=make_match("D A D G", "songsterr"))
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.tuning is None
    assert r.source is None
    assert r.candidates == ()
    assert r.failed == ("a",)
    assert r.needs_review is False
    assert cache.get("Tool", "Schism") is None
    assert cache.review_items() == []


def test_failure_with_non_exact_match_from_another_source_is_not_queued(cache):
    a = FakeSource("a", default=make_match("D A D G", "ug-bass", exact=False))
    b = failing_source("b")
    r = resolve("Tool", "Schism", [a, b], cache)
    assert r.failed == ("b",)
    assert r.candidates == ()
    assert r.needs_review is False
    assert cache.review_items() == []


def test_failed_lists_every_failed_source_in_source_order(cache):
    a = failing_source("a")
    b = FakeSource("b")
    c = failing_source("c")
    r = resolve("Tool", "Schism", [a, b, c], cache)
    assert r.failed == ("a", "c")


def test_failed_names_come_from_source_name_not_exception(cache):
    a = FakeSource("my-source", default=SourceError("whatever"))
    r = resolve("Tool", "Schism", [a], cache)
    assert r.failed == ("my-source",)


def test_disagreement_wins_over_failure(cache):
    m1 = make_match("E A D G", "ug-bass")
    m2 = make_match("D G C F", "songsterr")
    sources = [
        FakeSource("a", default=m1),
        failing_source("x"),
        FakeSource("b", default=m2),
    ]
    r = resolve("Tool", "Schism", sources, cache)
    assert r.tuning is None
    assert r.needs_review is True
    assert r.lookup_failed is False
    assert r.failed == ()
    assert r.candidates == (m1, m2)
    items = cache.review_items()
    assert [(i.artist, i.title) for i in items] == [("Tool", "Schism")]
    assert items[0].candidates == (m1, m2)


def test_failure_in_second_round_is_reported(cache):
    ug = FakeSource("ug", {(ARTIST, FULL): None, (ARTIST, PART): SourceError("down")})
    sg = FakeSource("songsterr")
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.failed == ("ug",)
    assert r.needs_review is False
    assert r.tuning is None
    assert cache.get(ARTIST, FULL) is None
    assert cache.review_items() == []
    assert ug.calls == [(ARTIST, FULL), (ARTIST, PART)]


def test_failure_in_first_round_only_is_reported_after_second_round(cache):
    ug = FakeSource("ug", {(ARTIST, FULL): SourceError("down"), (ARTIST, PART): None})
    r = resolve(ARTIST, FULL, [ug], cache)
    assert r.failed == ("ug",)
    assert cache.review_items() == []


def test_failures_in_different_rounds_are_merged_in_source_order(cache):
    ug = FakeSource("ug", {(ARTIST, FULL): SourceError("down")})
    sg = FakeSource("songsterr", {(ARTIST, PART): SourceError("down")})
    r = resolve(ARTIST, FULL, [ug, sg], cache)
    assert r.failed == ("ug", "songsterr")


def test_source_failing_in_both_rounds_listed_once(cache):
    ug = FakeSource("ug", default=SourceError("down"))
    r = resolve(ARTIST, FULL, [ug], cache)
    assert r.failed == ("ug",)


def test_second_round_disagreement_wins_over_failure(cache):
    ug_exact = make_match("A D G C F", "ug-bass", True, ARTIST, PART)
    sg_exact = make_match("B E A D G", "songsterr", True, ARTIST, PART)
    ug = FakeSource("ug", {(ARTIST, FULL): None, (ARTIST, PART): ug_exact})
    sg = FakeSource("songsterr", {(ARTIST, FULL): None, (ARTIST, PART): sg_exact})
    bad = FakeSource("bad", {(ARTIST, FULL): None, (ARTIST, PART): SourceError("down")})
    r = resolve(ARTIST, FULL, [ug, sg, bad], cache)
    assert r.needs_review is True
    assert r.failed == ()
    assert r.candidates == (ug_exact, sg_exact)


def test_cache_hit_wins_over_failing_source(cache):
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    a = failing_source("a")
    r = resolve("Tool", "Schism", [a], cache)
    assert a.calls == []
    assert r.source == "cache"
    assert r.failed == ()


# -------------------------------------------------------------- already queued / recheck


def test_queued_song_is_not_looked_up_again(cache):
    cands = [make_match("E A D G", "ug-bass", False, title="Schism (Live)")]
    cache.add_review("Tool", "Schism", cands)
    s = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [s], cache)
    assert s.calls == []
    assert r.tuning is None
    assert r.source is None
    assert r.candidates == tuple(cands)
    assert r.needs_review is True
    assert r.lookup_failed is False
    assert cache.get("Tool", "Schism") is None
    assert [(i.artist, i.title) for i in cache.review_items()] == [("Tool", "Schism")]


def test_queued_song_with_no_candidates(cache):
    cache.add_review("Tool", "Schism", [])
    s = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [s], cache)
    assert s.calls == []
    assert r.candidates == ()
    assert r.needs_review is True


def test_queued_check_uses_normalised_keys(cache):
    cands = [make_match("E A D G", "ug-bass")]
    cache.add_review("Tool", "Schism", cands)
    s = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("The Tool", "Schism (Remastered)", [s], cache)
    assert s.calls == []
    assert r.needs_review is True
    assert r.candidates == tuple(cands)


def test_resolve_twice_asks_sources_only_once(cache):
    s = FakeSource("a")
    r1 = resolve("Tool", "Schism", [s], cache)
    r2 = resolve("Tool", "Schism", [s], cache)
    assert r1.needs_review is True
    assert r2.needs_review is True
    assert s.calls == [("Tool", "Schism")]


def test_resolve_twice_keeps_disagreement_candidates(cache):
    m1 = make_match("E A D G", "ug-bass")
    m2 = make_match("D G C F", "songsterr")
    sources = [FakeSource("a", default=m1), FakeSource("b", default=m2)]
    resolve("Tool", "Schism", sources, cache)
    r = resolve("Tool", "Schism", sources, cache)
    assert r.candidates == (m1, m2)
    assert [len(s.calls) for s in sources] == [1, 1]


def test_cache_entry_wins_over_queue(cache):
    cache.add_review("Tool", "Schism", [])
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    r = resolve("Tool", "Schism", [FakeSource("a")], cache)
    assert r.source == "cache"
    assert r.needs_review is False


def test_recheck_asks_sources_again_and_accepts(cache):
    cache.add_review("Tool", "Schism", [])
    s = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [s], cache, recheck=True)
    assert s.calls == [("Tool", "Schism")]
    assert r.tuning == T("D A D G")
    assert r.source == "ug-bass"
    assert r.needs_review is False
    assert cache.get("Tool", "Schism") == Entry(T("D A D G"), "ug-bass", False)
    assert cache.review_items() == []
    assert cache.queued("Tool", "Schism") is None


def test_recheck_still_unresolved_stays_queued_with_new_candidates(cache):
    cache.add_review("Tool", "Schism", [])
    new = make_match("E A D G", "ug-bass", False, title="Schism (Live)")
    s = FakeSource("a", default=new)
    r = resolve("Tool", "Schism", [s], cache, recheck=True)
    assert s.calls == [("Tool", "Schism")]
    assert r.needs_review is True
    assert r.candidates == (new,)
    assert cache.queued("Tool", "Schism") == (new,)


def test_recheck_with_failure_is_a_lookup_failure(cache):
    cache.add_review("Tool", "Schism", [])
    a = failing_source("a")
    r = resolve("Tool", "Schism", [a], cache, recheck=True)
    assert a.calls
    assert r.failed == ("a",)
    assert r.needs_review is False
    assert cache.get("Tool", "Schism") is None


def test_recheck_without_queue_behaves_normally(cache):
    s = FakeSource("a", default=make_match("D A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [s], cache, recheck=True)
    assert r.source == "ug-bass"
    assert s.calls == [("Tool", "Schism")]


def test_recheck_does_not_override_cache_entry(cache):
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    s = FakeSource("a", default=make_match("E A D G", "ug-bass"))
    r = resolve("Tool", "Schism", [s], cache, recheck=True)
    assert r.source == "cache"
    assert s.calls == []
