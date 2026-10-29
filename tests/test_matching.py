from __future__ import annotations

import pytest

from bass_sort.matching import is_exact, is_similar


@pytest.mark.parametrize(
    "artist,title,o_artist,o_title",
    [
        ("Tool", "Schism", "Tool", "Schism (Remastered)"),
        ("Nirvana", "Come As You Are", "Nirvana", "Come As You Are - 2021 Remaster"),
        ("Artist", "Song", "Artist", "Song (feat. X)"),
        ("Artist", "Song", "Artist", "Song [Deluxe Edition]"),
        ("Artist", "Song", "Artist", "Song (Mono)"),
        ("The Beatles", "Help", "Beatles", "Help"),
        ("Beatles", "Help", "The Beatles", "Help"),
        ("Simon & Garfunkel", "Cecilia", "Simon and Garfunkel", "Cecilia"),
        ("TOOL", "SCHISM", "tool", "schism"),
        ("Tool", "Schism!", "Tool", "Schism"),
        ("Guns N' Roses", "Don't Cry", "Guns N Roses", "Dont Cry"),
        ("Tool", "Schism", "Tool", "Schism"),
    ],
)
def test_exact(artist, title, o_artist, o_title):
    assert is_exact(artist, title, o_artist, o_title)


def test_live_is_similar_not_exact():
    assert not is_exact("Tool", "Schism", "Tool", "Schism (Live)")
    assert is_similar("Tool", "Schism", "Tool", "Schism (Live)")


def test_different_artist_never_similar():
    assert not is_exact("Tool", "Schism", "Opeth", "Schism")
    assert not is_similar("Tool", "Schism", "Opeth", "Schism")
    assert not is_similar("Tool", "Schism", "Opeth", "Schism (Live)")


def test_unrelated_title_not_matching():
    assert not is_exact("Tool", "Schism", "Tool", "Parabola")
    assert not is_similar("Tool", "Schism", "Tool", "Parabola")
