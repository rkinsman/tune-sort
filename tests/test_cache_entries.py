"""Cache.entries() and Cache.delete()."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.conftest import T, make_match
from tune_sort.cache import Cache, CachedSong, Entry

E1 = Entry(T("D A D G"), "ug-bass", False)
E2 = Entry(T("E A D G"), "manual", True)

LEGACY_SCHEMA = """
CREATE TABLE tunings (song_key TEXT PRIMARY KEY, pitch_classes TEXT NOT NULL,
    source TEXT NOT NULL, confirmed INTEGER NOT NULL CHECK (confirmed IN (0, 1)));
CREATE TABLE review (song_key TEXT PRIMARY KEY, artist TEXT NOT NULL, title TEXT NOT NULL,
    candidates TEXT NOT NULL, queued_order INTEGER NOT NULL);
"""


def _make_legacy(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.executescript(LEGACY_SCHEMA)
        con.execute(
            "INSERT INTO tunings (song_key, pitch_classes, source, confirmed) VALUES (?, ?, ?, ?)",
            ("tool\x1fschism", "[2, 9, 2, 7]", "ug-pro", 0),
        )
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------------- entries


def test_entries_empty(cache):
    assert cache.entries() == []


def test_entries_returns_names_as_put(cache):
    cache.put("Tool", "Schism", E1)
    assert cache.entries() == [CachedSong("Tool", "Schism", E1)]


def test_entries_sorted_case_insensitively(cache):
    cache.put("tool", "Parabola", E1)
    cache.put("Tool", "schism", E2)
    cache.put("abba", "Waterloo", E1)
    cache.put("Beatles", "help", E1)
    cache.put("Beatles", "Abbey Road", E2)
    got = [(s.artist, s.title) for s in cache.entries()]
    assert got == [
        ("abba", "Waterloo"),
        ("Beatles", "Abbey Road"),
        ("Beatles", "help"),
        ("tool", "Parabola"),
        ("Tool", "schism"),
    ]


def test_entries_per_instrument(tmp_path):
    path = tmp_path / "c.db"
    g_entry = Entry(T("D A D G B E", "guitar"), "ug-pro", True)
    b = Cache(path)
    g = Cache(path, "guitar")
    try:
        b.put("Tool", "Schism", E1)
        g.put("Opeth", "Deliverance", g_entry)
        assert b.entries() == [CachedSong("Tool", "Schism", E1)]
        assert g.entries() == [CachedSong("Opeth", "Deliverance", g_entry)]
    finally:
        b.close()
        g.close()


def test_entries_unicode_round_trip(cache):
    cache.put("Sigur Rós", "Hoppípolla", E1)
    assert cache.entries() == [CachedSong("Sigur Rós", "Hoppípolla", E1)]


def test_entries_survive_reopen(tmp_path):
    path = tmp_path / "c.db"
    c = Cache(path)
    c.put("Tool", "Schism", E1)
    c.close()
    c2 = Cache(path)
    try:
        assert c2.entries() == [CachedSong("Tool", "Schism", E1)]
    finally:
        c2.close()


def test_entries_legacy_rows_use_normalised_names(tmp_path):
    path = tmp_path / "old.db"
    _make_legacy(path)
    c = Cache(path)
    try:
        assert c.entries() == [CachedSong("tool", "schism", Entry(T("D A D G"), "ug-pro", False))]
        assert c.get("Tool", "Schism") == Entry(T("D A D G"), "ug-pro", False)
    finally:
        c.close()


def test_put_after_legacy_fills_names(tmp_path):
    path = tmp_path / "old.db"
    _make_legacy(path)
    c = Cache(path)
    try:
        c.put("Tool", "Schism", E2)
        assert c.entries() == [CachedSong("Tool", "Schism", E2)]
    finally:
        c.close()


# ----------------------------------------------------------------------- delete


def test_delete_removes_entry(cache):
    cache.put("Tool", "Schism", E1)
    cache.delete("Tool", "Schism")
    assert cache.get("Tool", "Schism") is None
    assert cache.entries() == []


def test_delete_removes_queued_review(cache):
    cache.add_review("Tool", "Schism", [make_match("D A D G")])
    cache.delete("Tool", "Schism")
    assert cache.queued("Tool", "Schism") is None
    assert cache.review_items() == []


def test_delete_removes_entry_and_review_together(cache):
    cache.put("Tool", "Schism", E1)
    cache.add_review("Tool", "Schism", [make_match("D A D G")])
    cache.delete("Tool", "Schism")
    assert cache.get("Tool", "Schism") is None
    assert cache.queued("Tool", "Schism") is None


def test_delete_leaves_other_songs(cache):
    cache.put("Tool", "Schism", E1)
    cache.put("Tool", "Parabola", E2)
    cache.add_review("Opeth", "Deliverance", [])
    cache.delete("Tool", "Schism")
    assert cache.entries() == [CachedSong("Tool", "Parabola", E2)]
    assert cache.queued("Opeth", "Deliverance") == ()


def test_delete_missing_is_noop(cache):
    cache.put("Tool", "Schism", E1)
    assert cache.delete("Opeth", "Deliverance") is None
    assert cache.entries() == [CachedSong("Tool", "Schism", E1)]


def test_delete_on_empty_cache_is_noop(cache):
    assert cache.delete("Tool", "Schism") is None
    assert cache.entries() == []


def test_delete_matches_like_get(cache):
    cache.put("Tool", "Schism", E1)
    cache.delete("tool", "Schism (Remastered)")
    assert cache.get("Tool", "Schism") is None
    assert cache.entries() == []


def test_delete_only_affects_own_instrument(tmp_path):
    path = tmp_path / "c.db"
    g_entry = Entry(T("D A D G B E", "guitar"), "ug-pro", True)
    b = Cache(path)
    g = Cache(path, "guitar")
    try:
        b.put("Tool", "Schism", E1)
        g.put("Tool", "Schism", g_entry)
        b.delete("Tool", "Schism")
        assert b.get("Tool", "Schism") is None
        assert g.get("Tool", "Schism") == g_entry
    finally:
        b.close()
        g.close()
