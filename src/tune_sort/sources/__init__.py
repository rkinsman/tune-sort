"""Tab sites that can tell us the tuning a song's bass or guitar is played in."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Protocol

from tune_sort.tuning import Tuning

# Fetches a URL and returns the response body. Raises FetchError on failure.
Fetch = Callable[[str], str]


class FetchError(Exception):
    pass


@dataclass(frozen=True)
class Match:
    """A tuning a source found for a song."""

    tuning: Tuning
    source: str  # "ug-pro", "ug-bass" (bass), "ug-tab" (guitar) or "songsterr"
    url: str
    matched_artist: str
    matched_title: str
    exact: bool  # artist and title match the song (see tune_sort.matching)


class Source(Protocol):
    name: str

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        """Return the best match for the song, or None if nothing has a tuning for the
        source's instrument.

        Never raises for network or parse problems: those return None.
        """
        ...
