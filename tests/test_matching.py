from __future__ import annotations

import pytest

from bass_sort.matching import is_exact, is_similar, normalise_title, part_title


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
        (
            "TesseracT",
            "Of Matter - Retrospect",
            "TesseracT",
            "Of Matter - Retrospect - 2013 Remaster",
        ),
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


# ------------------------------------------------------------------ normalise_title


def test_normalise_title_ignores_trailing_remaster_suffix_after_part():
    assert normalise_title("Of Matter - Retrospect - 2013 Remaster") == normalise_title(
        "Of Matter - Retrospect"
    )


def test_normalise_title_keeps_part_name():
    assert "retrospect" in normalise_title("Of Matter - Retrospect - 2013 Remaster").lower()
    assert "retrospect" in normalise_title("Of Matter - Retrospect").lower()


def test_normalise_title_still_drops_single_remaster_suffix():
    assert normalise_title("Come As You Are - 2021 Remaster") == normalise_title(
        "Come As You Are"
    )


# --------------------------------------------------------------------- part_title


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Of Matter - Retrospect", "Retrospect"),
        ("Of Matter – Retrospect", "Retrospect"),
        ("Of Matter — Retrospect", "Retrospect"),
        ("Of Matter - Retrospect - 2013 Remaster", "Retrospect"),
        ("Of Mind - Nocturne (Remastered)", "Nocturne"),
    ],
)
def test_part_title_found(title, expected):
    assert part_title(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "Come As You Are - Live",
        "Song - Acoustic Version",
        "Song - Remix",
        "Song - Demo",
        "Song - Radio Edit",
        "Song - Unplugged",
        "Song - Instrumental",
        "Song - Mono",
        "Come As You Are - 2021 Remaster",
        "Schism",
        "Anti-Hero",
        "",
    ],
)
def test_part_title_none(title):
    assert part_title(title) is None
