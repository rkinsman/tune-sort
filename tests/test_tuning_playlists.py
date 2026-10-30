"""tuning.is_tuning_playlist."""
from __future__ import annotations

import pytest

from tune_sort.tuning import is_tuning_playlist

D = "–"  # en dash


@pytest.mark.parametrize(
    "name",
    [
        "Bass %s Drop D" % D,
        "Bass 5-String %s B Standard" % D,
        "Bass 6-String %s B E A D G C" % D,
    ],
)
def test_bass_tuning_playlists(name):
    assert is_tuning_playlist(name, "bass") is True


@pytest.mark.parametrize(
    "name",
    [
        "Guitar %s Drop D" % D,
        "Guitar 7-String %s B Standard" % D,
    ],
)
def test_guitar_tuning_playlists(name):
    assert is_tuning_playlist(name, "guitar") is True


@pytest.mark.parametrize(
    "name",
    [
        "Guitar %s Drop D" % D,
        "Guitar 7-String %s B Standard" % D,
        "Bass - Drop D",
        "Bass-Drop D",
        "Bassline",
        "Bass %s" % D,
        "Bass %s " % D,
        "Bass5-String %s X" % D,
        "Bass - 5-String %s X" % D,
        "My Bass %s Drop D" % D,
        "Road Trip",
        "",
    ],
)
def test_not_bass_tuning_playlists(name):
    assert is_tuning_playlist(name, "bass") is False


@pytest.mark.parametrize(
    "name",
    [
        "Bass %s Drop D" % D,
        "Bass 5-String %s B Standard" % D,
        "Guitar - Drop D",
        "Guitarist",
        "Guitar %s" % D,
        "Guitar7-String %s X" % D,
        "Road Trip",
    ],
)
def test_not_guitar_tuning_playlists(name):
    assert is_tuning_playlist(name, "guitar") is False
