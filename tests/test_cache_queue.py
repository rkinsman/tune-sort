"""Cache.queued, Cache.review_items(songs) and titles that normalise to nothing."""
from __future__ import annotations

from conftest import T, make_match

from tune_sort.cache import Cache, Entry, ReviewItem

C1 = [make_match("D A D G"), make_match("E A D G", "songsterr", False, title="Schism (Live)")]
C2 = [make_match("C G C F", artist="Opeth", title="Deliverance")]


# ------------------------------------------------------------------------ queued


def test_queued_none_when_not_queued(cache):
    assert cache.queued("Tool", "Schism") is None


def test_queued_returns_candidates(cache):
    cache.add_review("Tool", "Schism", C1)
    assert cache.queued("Tool", "Schism") == tuple(C1)


def test_queued_empty_candidates_is_empty_tuple_not_none(cache):
    cache.add_review("Tool", "Schism", [])
    got = cache.queued("Tool", "Schism")
    assert got == ()
    assert got is not None


def test_queued_is_normalised(cache):
    cache.add_review("Tool", "Schism", C1)
    assert cache.queued("Tool", "Schism (Remastered)") == tuple(C1)
    assert cache.queued("The Tool", "Schism") == tuple(C1)
    assert cache.queued("tool", "SCHISM") == tuple(C1)
    assert cache.queued("Tool", "Parabola") is None


def test_queued_normalised_when_added_with_decorated_title(cache):
    cache.add_review("The Tool", "Schism (Remastered)", C1)
    assert cache.queued("Tool", "Schism") == tuple(C1)


def test_queued_none_after_put(cache):
    cache.add_review("Tool", "Schism", C1)
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    assert cache.queued("Tool", "Schism") is None


def test_queued_reflects_replaced_candidates(cache):
    cache.add_review("Tool", "Schism", C1)
    cache.add_review("Tool", "Schism", C2)
    assert cache.queued("Tool", "Schism") == tuple(C2)


def test_queued_is_per_instrument(tmp_path):
    path = tmp_path / "c.db"
    bass = Cache(path, "bass")
    guitar = Cache(path, "guitar")
    try:
        bass.add_review("Tool", "Schism", C1)
        assert bass.queued("Tool", "Schism") == tuple(C1)
        assert guitar.queued("Tool", "Schism") is None
    finally:
        bass.close()
        guitar.close()


def test_queued_survives_reopen(tmp_path):
    path = tmp_path / "c.db"
    c = Cache(path)
    c.add_review("Tool", "Schism", C1)
    c.close()
    c2 = Cache(path)
    try:
        assert c2.queued("Tool", "Schism") == tuple(C1)
    finally:
        c2.close()


# -------------------------------------------------------------- review_items(songs)


def _queue(cache):
    cache.add_review("Tool", "Schism", C1)
    cache.add_review("Opeth", "Deliverance", C2)
    cache.add_review("Rush", "YYZ", [])


def test_review_items_no_argument_unchanged(cache):
    _queue(cache)
    assert [(i.artist, i.title) for i in cache.review_items()] == [
        ("Tool", "Schism"),
        ("Opeth", "Deliverance"),
        ("Rush", "YYZ"),
    ]
    assert [(i.artist, i.title) for i in cache.review_items(None)] == [
        ("Tool", "Schism"),
        ("Opeth", "Deliverance"),
        ("Rush", "YYZ"),
    ]


def test_review_items_empty_songs_gives_empty_list(cache):
    _queue(cache)
    assert cache.review_items([]) == []
    assert cache.review_items(iter(())) == []


def test_review_items_filters_to_given_songs(cache):
    _queue(cache)
    items = cache.review_items([("Opeth", "Deliverance")])
    assert items == [ReviewItem("Opeth", "Deliverance", tuple(C2))]


def test_review_items_ignores_songs_not_queued(cache):
    _queue(cache)
    assert cache.review_items([("Muse", "Hysteria"), ("Rush", "YYZ")]) == [
        ReviewItem("Rush", "YYZ", ())
    ]


def test_review_items_keeps_queue_order_not_argument_order(cache):
    _queue(cache)
    items = cache.review_items([("Rush", "YYZ"), ("Tool", "Schism")])
    assert [(i.artist, i.title) for i in items] == [("Tool", "Schism"), ("Rush", "YYZ")]


def test_review_items_songs_are_normalised(cache):
    _queue(cache)
    items = cache.review_items([("The Tool", "Schism (Remastered)"), ("opeth", "DELIVERANCE")])
    assert [(i.artist, i.title) for i in items] == [("Tool", "Schism"), ("Opeth", "Deliverance")]


def test_review_items_accepts_generator(cache):
    _queue(cache)
    items = cache.review_items((a, t) for a, t in [("Tool", "Schism")])
    assert [(i.artist, i.title) for i in items] == [("Tool", "Schism")]


def test_review_items_duplicate_songs_listed_once(cache):
    _queue(cache)
    items = cache.review_items([("Tool", "Schism"), ("Tool", "Schism")])
    assert [(i.artist, i.title) for i in items] == [("Tool", "Schism")]


# ------------------------------------------------ titles that normalise to nothing


def test_punctuation_only_titles_have_separate_entries(cache):
    cache.put("Artist", "…", Entry(T("D A D G"), "manual", True))
    assert cache.get("Artist", "?!") is None
    assert cache.get("Artist", "…") == Entry(T("D A D G"), "manual", True)


def test_punctuation_only_titles_do_not_overwrite_each_other(cache):
    cache.put("Artist", "…", Entry(T("D A D G"), "manual", True))
    cache.put("Artist", "?!", Entry(T("E A D G"), "manual", True))
    assert cache.get("Artist", "…") == Entry(T("D A D G"), "manual", True)
    assert cache.get("Artist", "?!") == Entry(T("E A D G"), "manual", True)


def test_punctuation_only_titles_have_separate_queue_items(cache):
    cache.add_review("Artist", "…", C1)
    assert cache.queued("Artist", "?!") is None
    assert cache.queued("Artist", "…") == tuple(C1)
    cache.put("Artist", "?!", Entry(T("D A D G"), "manual", True))
    assert cache.queued("Artist", "…") == tuple(C1)
