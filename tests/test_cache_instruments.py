"""Cache behaviour with separate bass and guitar data in one file."""
from __future__ import annotations

import dataclasses

from tests.conftest import T, make_match
from tune_sort.cache import Cache, Entry, ReviewItem
from tune_sort.tuning import Tuning

GUITAR_E_STD = Tuning((4, 9, 2, 7, 11, 4), "guitar")


def test_guitar_entry_round_trip(guitar_cache):
    entry = Entry(T("D A D G B E", "guitar"), "ug-pro", False)
    guitar_cache.put("Tool", "Schism", entry)
    got = guitar_cache.get("Tool", "Schism")
    assert got == entry
    assert got.tuning.instrument == "guitar"
    assert got.tuning.name == "Drop D"


def test_guitar_six_string_not_reduced_on_read(guitar_cache):
    guitar_cache.put("Tool", "Schism", Entry(GUITAR_E_STD, "manual", True))
    got = guitar_cache.get("Tool", "Schism")
    assert got == Entry(GUITAR_E_STD, "manual", True)
    assert got.tuning.string_count == 6


def test_bass_cache_still_reduces_guitar_shaped_bass_tuning(cache):
    cache.put("Tool", "Schism", Entry(Tuning((4, 9, 2, 7, 11, 4)), "ug-bass", False))
    assert cache.get("Tool", "Schism").tuning == Tuning((4, 9, 2, 7))


def test_guitar_review_candidates_round_trip(guitar_cache):
    cands = [
        make_match("D A D G B E", "ug-pro", True, instrument="guitar"),
        make_match("E A D G B E", "songsterr", False, title="Schism (Live)", instrument="guitar"),
    ]
    guitar_cache.add_review("Tool", "Schism", cands)
    items = guitar_cache.review_items()
    assert items == [ReviewItem("Tool", "Schism", tuple(cands))]
    assert items[0].candidates[1].tuning.string_count == 6
    assert all(c.tuning.instrument == "guitar" for c in items[0].candidates)


def test_bass_and_guitar_entries_independent_in_one_file(tmp_path):
    path = tmp_path / "c.db"
    bass_entry = Entry(T("D A D G"), "ug-bass", False)
    guitar_entry = Entry(T("D A D G B E", "guitar"), "ug-pro", True)
    b = Cache(path)
    g = Cache(path, "guitar")
    try:
        b.put("Tool", "Schism", bass_entry)
        assert g.get("Tool", "Schism") is None
        g.put("Tool", "Schism", guitar_entry)
        assert b.get("Tool", "Schism") == bass_entry
        assert g.get("Tool", "Schism") == guitar_entry
    finally:
        b.close()
        g.close()


def test_review_queues_independent(tmp_path):
    path = tmp_path / "c.db"
    b = Cache(path)
    g = Cache(path, "guitar")
    try:
        b.add_review("Tool", "Schism", [make_match("D A D G")])
        assert g.review_items() == []
        g.add_review("Opeth", "Deliverance", [])
        g.add_review("Tool", "Schism", [make_match("D A D G B E", instrument="guitar")])
        assert [(i.artist, i.title) for i in b.review_items()] == [("Tool", "Schism")]
        assert [(i.artist, i.title) for i in g.review_items()] == [
            ("Opeth", "Deliverance"),
            ("Tool", "Schism"),
        ]
        # Resolving a song for one instrument leaves the other's queue alone.
        g.put("Tool", "Schism", Entry(T("D A D G B E", "guitar"), "manual", True))
        assert [(i.artist, i.title) for i in g.review_items()] == [("Opeth", "Deliverance")]
        assert [(i.artist, i.title) for i in b.review_items()] == [("Tool", "Schism")]
        b.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
        assert b.review_items() == []
        assert [(i.artist, i.title) for i in g.review_items()] == [("Opeth", "Deliverance")]
    finally:
        b.close()
        g.close()


def test_default_instrument_reads_bass_data(tmp_path):
    # Data written with the default (bass) constructor, as an earlier version would.
    path = tmp_path / "c.db"
    entry = Entry(T("D A D G"), "ug-bass", True)
    cand = make_match("E A D G")
    old = Cache(path)
    old.put("Tool", "Schism", entry)
    old.add_review("Opeth", "Deliverance", [cand])
    old.close()

    bass = Cache(path, "bass")
    guitar = Cache(path, "guitar")
    try:
        assert bass.get("Tool", "Schism") == entry
        assert bass.review_items() == [ReviewItem("Opeth", "Deliverance", (cand,))]
        assert guitar.get("Tool", "Schism") is None
        assert guitar.review_items() == []
    finally:
        bass.close()
        guitar.close()


def test_guitar_data_survives_reopen(tmp_path):
    path = tmp_path / "c.db"
    entry = Entry(GUITAR_E_STD, "songsterr", False)
    cand = dataclasses.replace(
        make_match("D A D G B E", instrument="guitar"), source="ug-tab", url="https://x/t"
    )
    g = Cache(path, "guitar")
    g.put("Tool", "Schism", entry)
    g.add_review("Opeth", "Deliverance", [cand])
    g.close()
    g2 = Cache(path, "guitar")
    try:
        assert g2.get("Tool", "Schism") == entry
        assert g2.review_items() == [ReviewItem("Opeth", "Deliverance", (cand,))]
    finally:
        g2.close()
