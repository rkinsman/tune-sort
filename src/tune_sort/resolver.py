"""Working out one bass tuning per song from the cache and the sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Optional

from tune_sort.cache import Cache, Entry
from tune_sort.matching import part_title
from tune_sort.sources import Match, Source
from tune_sort.tuning import Tuning


@dataclass(frozen=True)
class Resolution:
    artist: str
    title: str
    tuning: Optional[Tuning]  # None when the song needs review
    source: Optional[str]  # "cache", or the Match.source that found it; None for review
    candidates: tuple[Match, ...] = field(default=())  # fuzzy matches, when needing review

    @property
    def needs_review(self) -> bool:
        return self.tuning is None


def resolve(artist: str, title: str, sources: Sequence[Source], cache: Cache) -> Resolution:
    """Resolve a song's tuning.

    1. A cache entry wins and no source is asked.
    2. Otherwise every source is asked, in order. The first exact match is accepted, stored
       in the cache and returned, unless another source's exact match has a different
       tuning: then the song is queued for review with the exact matches followed by
       the non-exact ones.
    3. If no source matched exactly and the title has a part name
       (matching.part_title, e.g. "Retrospect" for "Of Matter - Retrospect"), every
       source is asked again with the part name, and exact matches from that second
       round count as exact under rule 2. Non-exact matches from both rounds are kept,
       dropping any with the same source and url as a match already kept. The result is
       cached under the original title.
    4. With still no exact match, the song is queued for review with the non-exact
       matches.
    Songs queued for review are returned with tuning None.
    """
    cached = cache.get(artist, title)
    if cached is not None:
        return Resolution(artist, title, cached.tuning, "cache")

    exact, fuzzy = _ask(sources, artist, title)
    part = part_title(title)
    if not exact and part is not None:
        exact, more_fuzzy = _ask(sources, artist, part)
        seen = {(m.source, m.url) for m in exact}
        kept: list[Match] = []
        for m in fuzzy + more_fuzzy:
            if (m.source, m.url) not in seen:
                seen.add((m.source, m.url))
                kept.append(m)
        fuzzy = kept

    if exact and all(m.tuning == exact[0].tuning for m in exact):
        primary = exact[0]
        cache.put(artist, title, Entry(primary.tuning, primary.source, confirmed=False))
        return Resolution(artist, title, primary.tuning, primary.source)

    candidates = exact + fuzzy
    cache.add_review(artist, title, candidates)
    return Resolution(artist, title, None, None, tuple(candidates))


def _ask(sources: Sequence[Source], artist: str, title: str) -> tuple[list[Match], list[Match]]:
    """Ask every source; return (exact matches, non-exact matches), each in source order."""
    exact: list[Match] = []
    fuzzy: list[Match] = []
    for source in sources:
        match = source.lookup(artist, title)
        if match is not None:
            (exact if match.exact else fuzzy).append(match)
    return exact, fuzzy
