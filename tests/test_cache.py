from __future__ import annotations

from pathlib import Path

from conftest import T, make_match

from bass_sort.cache import Cache, Entry, ReviewItem


def test_get_missing(cache):
    assert cache.get("Tool", "Schism") is None
    assert cache.review_items() == []


def test_round_trip(cache):
    entry = Entry(T("D A D G"), "ug-bass", False)
    cache.put("Tool", "Schism", entry)
    assert cache.get("Tool", "Schism") == entry


def test_round_trip_confirmed_manual_five_string(cache):
    entry = Entry(T("B E A D G"), "manual", True)
    cache.put("Tool", "Schism", entry)
    got = cache.get("Tool", "Schism")
    assert got == entry
    assert got.confirmed is True
    assert got.source == "manual"
    assert got.tuning.string_count == 5


def test_keys_are_normalised(cache):
    entry = Entry(T("D A D G"), "songsterr", False)
    cache.put("Tool", "Schism", entry)
    assert cache.get("Tool", "Schism (Remastered)") == entry
    assert cache.get("tool", "SCHISM") == entry
    assert cache.get("Tool", "Parabola") is None


def test_put_replaces(cache):
    cache.put("Tool", "Schism", Entry(T("E A D G"), "ug-pro", False))
    new = Entry(T("D A D G"), "manual", True)
    cache.put("Tool", "Schism", new)
    assert cache.get("Tool", "Schism") == new


def test_review_queue_order_and_candidates(cache):
    c1 = [make_match("D A D G"), make_match("E A D G", "songsterr", False, title="Schism (Live)")]
    c2 = [make_match("C G C F", artist="Opeth", title="Deliverance")]
    cache.add_review("Tool", "Schism", c1)
    cache.add_review("Opeth", "Deliverance", c2)
    items = cache.review_items()
    assert items == [
        ReviewItem("Tool", "Schism", tuple(c1)),
        ReviewItem("Opeth", "Deliverance", tuple(c2)),
    ]


def test_add_review_replaces_candidates(cache):
    cache.add_review("Tool", "Schism", [make_match("E A D G")])
    new = [make_match("D A D G")]
    cache.add_review("Tool", "Schism", new)
    items = cache.review_items()
    assert len(items) == 1
    assert items[0].candidates == tuple(new)


def test_review_with_no_candidates(cache):
    cache.add_review("Tool", "Schism", [])
    items = cache.review_items()
    assert len(items) == 1
    assert items[0].candidates == ()


def test_put_removes_from_review(cache):
    cache.add_review("Tool", "Schism", [make_match("E A D G")])
    cache.add_review("Opeth", "Deliverance", [])
    cache.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    assert [(i.artist, i.title) for i in cache.review_items()] == [("Opeth", "Deliverance")]


def test_put_removes_from_review_using_normalised_key(cache):
    cache.add_review("Tool", "Schism", [])
    cache.put("Tool", "Schism (Remastered)", Entry(T("D A D G"), "manual", True))
    assert cache.review_items() == []


def test_survives_reopen(tmp_path):
    path = tmp_path / "c.db"
    c = Cache(path)
    entry = Entry(T("D A D G"), "ug-bass", True)
    cands = [make_match("E A D G")]
    c.put("Tool", "Schism", entry)
    c.add_review("Opeth", "Deliverance", cands)
    c.close()
    c2 = Cache(path)
    try:
        assert c2.get("Tool", "Schism") == entry
        assert c2.review_items() == [ReviewItem("Opeth", "Deliverance", tuple(cands))]
    finally:
        c2.close()


def test_creates_parent_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "c" / "t.db"
    c = Cache(path)
    c.close()
    assert Path(path).parent.is_dir()
    assert path.exists()
