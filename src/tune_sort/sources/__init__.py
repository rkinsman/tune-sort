"""Tab sites that can tell us the tuning a song's bass or guitar is played in."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional, Protocol

from tune_sort.tuning import Tuning

# Fetches a URL and returns the response body. Raises FetchError on failure.
Fetch = Callable[[str], str]


class FetchError(Exception):
    pass


class SourceError(Exception):
    """A lookup couldn't finish because a fetch failed, so the answer is unknown (as
    opposed to None: the source has no tuning for the song)."""


@dataclass(frozen=True)
class Match:
    """A tuning a source found for a song."""

    tuning: Tuning
    source: str  # "ug-pro", "ug-bass" (bass), "ug-tab" (guitar) or "songsterr"
    url: str
    matched_artist: str
    matched_title: str
    exact: bool  # artist and title match the song (see tune_sort.matching)


def memoize(fetch: Fetch, maxsize: int = 64) -> Fetch:
    """Wrap a Fetch so each URL is fetched at most once while it is among the `maxsize`
    most recently used URLs; later calls return the stored body. A FetchError is not
    stored: the next call for that URL tries again."""
    bodies: OrderedDict[str, str] = OrderedDict()

    def memoized(url: str) -> str:
        if url in bodies:
            bodies.move_to_end(url)
        else:
            bodies[url] = fetch(url)
            if len(bodies) > maxsize:
                bodies.popitem(last=False)
        return bodies[url]

    return memoized


class Source(Protocol):
    name: str

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        """Return the best match for the song, or None if nothing has a tuning for the
        source's instrument.

        Raises SourceError when a fetch fails, so the answer is unknown. Parse problems
        (unexpected page or JSON layout) return None.
        """
        ...
