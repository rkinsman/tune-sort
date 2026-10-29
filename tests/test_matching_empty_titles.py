"""Titles that normalise to nothing keep a distinguishing key."""
from __future__ import annotations

import pytest

from tune_sort.matching import is_exact, normalise_title


@pytest.mark.parametrize(
    "title,expected",
    [
        ("…", "…"),
        ("?!", "?!"),
        (" ?! ", "?!"),
        ("?!   ?!", "?! ?!"),
        ("  …  ", "…"),
    ],
)
def test_normalise_title_of_punctuation_only_title(title, expected):
    assert normalise_title(title) == expected


@pytest.mark.parametrize("title", ["", " ", "   ", "\t"])
def test_normalise_title_blank_is_empty(title):
    assert normalise_title(title) == ""


def test_normalise_title_unchanged_for_normal_titles():
    assert normalise_title("Schism!") == normalise_title("Schism")
    assert normalise_title("SCHISM") == normalise_title("schism")
    assert normalise_title("Schism") != ""
    assert normalise_title("Schism (Remastered)") == normalise_title("Schism")


def test_punctuation_titles_are_not_exact_with_each_other():
    assert is_exact("A", "…", "A", "?!") is False


def test_same_punctuation_title_is_exact():
    assert is_exact("A", "…", "A", "…") is True
    assert is_exact("A", "?!", "A", " ?! ") is True


def test_punctuation_title_is_not_exact_with_normal_title():
    assert is_exact("A", "…", "A", "Schism") is False
