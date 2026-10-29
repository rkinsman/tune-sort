"""Tab sites that can tell us a song's bass tuning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Protocol

from bass_sort.tuning import Tuning

# Fetches a URL and returns the response body. Raises FetchError on failure.
Fetch = Callable[[str], str]


class FetchError(Exception):
    pass


@dataclass(frozen=True)
class Match:
    """A tuning a source found for a song."""

    tuning: Tuning
    source: str  # "ug-pro", "ug-bass" or "songsterr"
    url: str
    matched_artist: str
    matched_title: str
    exact: bool  # artist and title match the song (see bass_sort.matching)


class Source(Protocol):
    name: str

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        """Return the best match for the song, or None if nothing has a bass tuning.

        Never raises for network or parse problems: those return None.
        """
        ...
