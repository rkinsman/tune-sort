"""SQLite cache of resolved tunings and the review queue."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from tune_sort import matching
from tune_sort.sources import Match
from tune_sort.tuning import Instrument, Tuning, from_pitch_classes

DEFAULT_PATH = Path.home() / ".cache" / "tune-sort" / "tunings.db"
# Where the cache lived before the project was renamed from bass-tuning-sorter.
LEGACY_PATH = Path.home() / ".cache" / "bass-tuning-sorter" / "tunings.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tunings (
    song_key TEXT PRIMARY KEY,
    pitch_classes TEXT NOT NULL,
    source TEXT NOT NULL,
    confirmed INTEGER NOT NULL CHECK (confirmed IN (0, 1))
);
CREATE TABLE IF NOT EXISTS review (
    song_key TEXT PRIMARY KEY,
    artist TEXT NOT NULL,
    title TEXT NOT NULL,
    candidates TEXT NOT NULL,
    queued_order INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Entry:
    tuning: Tuning
    source: str  # a source's Match.source, or "manual"
    confirmed: bool  # set by the user rather than a lookup


@dataclass(frozen=True)
class CachedSong:
    artist: str  # display names as given to put (normalised for legacy rows)
    title: str
    entry: Entry


@dataclass(frozen=True)
class ReviewItem:
    artist: str
    title: str
    candidates: tuple[Match, ...]  # fuzzy matches found, possibly empty


def migrate_legacy_cache(legacy: Path = LEGACY_PATH, new: Path = DEFAULT_PATH) -> bool:
    """Move the cache file from `legacy` to `new` (creating new's parent directories) when
    `legacy` exists and `new` doesn't. Returns True if it moved the file. Never
    overwrites an existing `new`."""
    if new.exists() or not legacy.is_file():
        return False
    new.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(new))
    return True


def _key(artist: str, title: str, instrument: Instrument) -> str:
    key = matching.normalise_artist(artist) + "\x1f" + matching.normalise_title(title)
    # Bass keys keep the format earlier, bass-only versions wrote.
    return key if instrument == "bass" else f"{instrument}\x1e{key}"


def _key_instrument(key: str) -> str:
    # Compared by prefix, not by recomputing the key: normalisation may have changed
    # since the row was written.
    return key.split("\x1e", 1)[0] if "\x1e" in key else "bass"


def _match_to_json(m: Match) -> dict[str, Any]:
    return {
        "tuning": list(m.tuning.pitch_classes),
        "source": m.source,
        "url": m.url,
        "matched_artist": m.matched_artist,
        "matched_title": m.matched_title,
        "exact": m.exact,
    }


def _match_from_json(d: dict[str, Any], instrument: Instrument) -> Match:
    return Match(
        tuning=from_pitch_classes(d["tuning"], instrument),
        source=d["source"],
        url=d["url"],
        matched_artist=d["matched_artist"],
        matched_title=d["matched_title"],
        exact=d["exact"],
    )


class Cache:
    """Keyed by normalised artist and title (tune_sort.matching), so "Schism" and
    "Schism (Remastered)" by "Tool" share an entry. Creates the file and parent
    directories if missing. Data survives reopening the same path.

    Tunings read back (entries and review candidates) get the same guitar-tuning
    reduction as tuning.parse_note_names, so a 6-string guitar tuning stored by an
    older version, e.g. E A D G B E, comes back as its lowest four strings.

    A Cache is opened for one instrument. Bass and guitar entries and review queues in the
    same file are independent: the same song can have a bass and a guitar entry. Files
    written by earlier versions (bass only) read as bass. The guitar-tuning reduction on
    read applies to bass only."""

    def __init__(self, path: Path = DEFAULT_PATH, instrument: Instrument = "bass") -> None:
        self.instrument: Instrument = instrument
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)

    def get(self, artist: str, title: str) -> Optional[Entry]:
        row = self._db.execute(
            "SELECT pitch_classes, source, confirmed FROM tunings WHERE song_key = ?",
            (self._key(artist, title),),
        ).fetchone()
        if row is None:
            return None
        tuning = from_pitch_classes(json.loads(row[0]), self.instrument)
        return Entry(tuning, row[1], bool(row[2]))

    def put(self, artist: str, title: str, entry: Entry) -> None:
        """Store an entry, replacing any existing one, and remove the song from the
        review queue."""
        key = self._key(artist, title)
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO tunings VALUES (?, ?, ?, ?)",
                (
                    key,
                    json.dumps(list(entry.tuning.pitch_classes)),
                    entry.source,
                    int(entry.confirmed),
                ),
            )
            self._db.execute("DELETE FROM review WHERE song_key = ?", (key,))

    def entries(self) -> list[CachedSong]:
        """All entries for this cache's instrument, sorted case-insensitively by artist,
        then title. Rows written before display names were stored use the normalised
        names."""
        raise NotImplementedError

    def delete(self, artist: str, title: str) -> None:
        """Remove the song's entry and its review-queue item, matching as get does.
        Does nothing if the song is not cached."""
        raise NotImplementedError

    def add_review(self, artist: str, title: str, candidates: list[Match]) -> None:
        """Queue a song for review, replacing its candidates if it is already queued."""
        key = self._key(artist, title)
        blob = json.dumps([_match_to_json(m) for m in candidates])
        with self._db:
            updated = self._db.execute(
                "UPDATE review SET candidates = ? WHERE song_key = ?", (blob, key)
            ).rowcount
            if not updated:
                self._db.execute(
                    "INSERT INTO review VALUES (?, ?, ?, ?,"
                    " (SELECT COALESCE(MAX(queued_order), 0) + 1 FROM review))",
                    (key, artist, title, blob),
                )

    def queued(self, artist: str, title: str) -> Optional[tuple[Match, ...]]:
        """The song's review candidates if it is queued for review, else None."""
        row = self._db.execute(
            "SELECT candidates FROM review WHERE song_key = ?", (self._key(artist, title),)
        ).fetchone()
        if row is None:
            return None
        return tuple(_match_from_json(d, self.instrument) for d in json.loads(row[0]))

    def review_items(self, songs: Optional[Iterable[tuple[str, str]]] = None) -> list[ReviewItem]:
        """Queued songs in the order they were first queued. With `songs`, (artist, title)
        pairs, only the queued songs among them (matched as cache keys are)."""
        keys = None if songs is None else {self._key(a, t) for a, t in songs}
        rows = self._db.execute(
            "SELECT song_key, artist, title, candidates FROM review ORDER BY queued_order"
        ).fetchall()
        return [
            ReviewItem(a, t, tuple(_match_from_json(d, self.instrument) for d in json.loads(c)))
            for key, a, t, c in rows
            if _key_instrument(key) == self.instrument and (keys is None or key in keys)
        ]

    def _key(self, artist: str, title: str) -> str:
        return _key(artist, title, self.instrument)

    def close(self) -> None:
        self._db.close()
