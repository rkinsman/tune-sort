from __future__ import annotations

import dataclasses
from pathlib import Path

from conftest import T, make_match

from bass_sort.cache import Cache, Entry, ReviewItem
from bass_sort.tuning import Tuning

# A 6-string guitar tuning built directly, as an older version may have stored it.
OLD_GUITAR = Tuning((4, 9, 2, 7, 11, 4))
E_STANDARD = Tuning((4, 9, 2, 7))
SIX_STRING_BASS = Tuning((11, 4, 9, 2, 7, 0))


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


# ------------------------------------- old 6-string guitar tunings reduce on read


def test_old_guitar_tuning_entry_reads_back_reduced(cache):
    cache.put("Tool", "Schism", Entry(OLD_GUITAR, "ug-bass", False))
    got = cache.get("Tool", "Schism")
    assert got is not None
    assert got.tuning == E_STANDARD
    assert got.tuning.string_count == 4
    assert got.tuning.name == "E Standard"
    assert got.source == "ug-bass"
    assert got.confirmed is False


def test_old_guitar_tuning_keeps_source_and_confirmed(cache):
    cache.put("Tool", "Schism", Entry(OLD_GUITAR, "manual", True))
    got = cache.get("Tool", "Schism")
    assert got == Entry(E_STANDARD, "manual", True)


def test_old_guitar_tuning_reduced_after_reopen(tmp_path):
    path = tmp_path / "c.db"
    c = Cache(path)
    c.put("Tool", "Schism", Entry(OLD_GUITAR, "songsterr", True))
    c.close()
    c2 = Cache(path)
    try:
        assert c2.get("Tool", "Schism") == Entry(E_STANDARD, "songsterr", True)
    finally:
        c2.close()


def test_old_guitar_tuning_in_review_candidate_reduced(cache):
    old = dataclasses.replace(make_match("E A D G"), tuning=OLD_GUITAR)
    cache.add_review("Tool", "Schism", [old])
    items = cache.review_items()
    assert len(items) == 1
    (cand,) = items[0].candidates
    assert cand.tuning == E_STANDARD
    assert cand.tuning.string_count == 4
    assert cand.source == old.source
    assert cand.url == old.url
    assert cand.matched_artist == old.matched_artist
    assert cand.matched_title == old.matched_title
    assert cand.exact == old.exact


def test_old_guitar_candidate_reduced_after_reopen(tmp_path):
    path = tmp_path / "c.db"
    old = dataclasses.replace(make_match("E A D G"), tuning=OLD_GUITAR)
    c = Cache(path)
    c.add_review("Tool", "Schism", [old])
    c.close()
    c2 = Cache(path)
    try:
        assert c2.review_items()[0].candidates[0].tuning == E_STANDARD
    finally:
        c2.close()


def test_real_six_string_bass_entry_unchanged(cache):
    entry = Entry(SIX_STRING_BASS, "ug-bass", False)
    cache.put("Tool", "Schism", entry)
    got = cache.get("Tool", "Schism")
    assert got == entry
    assert got.tuning.string_count == 6


def test_real_six_string_bass_candidate_unchanged(cache):
    cand = dataclasses.replace(make_match("E A D G"), tuning=SIX_STRING_BASS)
    cache.add_review("Tool", "Schism", [cand])
    assert cache.review_items()[0].candidates == (cand,)
