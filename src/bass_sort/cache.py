"""SQLite cache of resolved tunings and the review queue."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bass_sort import matching
from bass_sort.sources import Match
from bass_sort.tuning import Tuning, from_pitch_classes

DEFAULT_PATH = Path.home() / ".cache" / "bass-tuning-sorter" / "tunings.db"

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
class ReviewItem:
    artist: str
    title: str
    candidates: tuple[Match, ...]  # fuzzy matches found, possibly empty


def _key(artist: str, title: str) -> str:
    return matching.normalise_artist(artist) + "\x1f" + matching.normalise_title(title)


def _match_to_json(m: Match) -> dict[str, Any]:
    return {
        "tuning": list(m.tuning.pitch_classes),
        "source": m.source,
        "url": m.url,
        "matched_artist": m.matched_artist,
        "matched_title": m.matched_title,
        "exact": m.exact,
    }


def _match_from_json(d: dict[str, Any]) -> Match:
    return Match(
        tuning=from_pitch_classes(d["tuning"]),
        source=d["source"],
        url=d["url"],
        matched_artist=d["matched_artist"],
        matched_title=d["matched_title"],
        exact=d["exact"],
    )


class Cache:
    """Keyed by normalised artist and title (bass_sort.matching), so "Schism" and
    "Schism (Remastered)" by "Tool" share an entry. Creates the file and parent
    directories if missing. Data survives reopening the same path.

    Tunings read back (entries and review candidates) get the same guitar-tuning
    reduction as tuning.parse_note_names, so a 6-string guitar tuning stored by an
    older version, e.g. E A D G B E, comes back as its lowest four strings."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)

    def get(self, artist: str, title: str) -> Optional[Entry]:
        row = self._db.execute(
            "SELECT pitch_classes, source, confirmed FROM tunings WHERE song_key = ?",
            (_key(artist, title),),
        ).fetchone()
        if row is None:
            return None
        return Entry(from_pitch_classes(json.loads(row[0])), row[1], bool(row[2]))

    def put(self, artist: str, title: str, entry: Entry) -> None:
        """Store an entry, replacing any existing one, and remove the song from the
        review queue."""
        key = _key(artist, title)
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

    def add_review(self, artist: str, title: str, candidates: list[Match]) -> None:
        """Queue a song for review, replacing its candidates if it is already queued."""
        key = _key(artist, title)
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

    def review_items(self) -> list[ReviewItem]:
        """Queued songs in the order they were first queued."""
        rows = self._db.execute(
            "SELECT artist, title, candidates FROM review ORDER BY queued_order"
        ).fetchall()
        return [
            ReviewItem(a, t, tuple(_match_from_json(d) for d in json.loads(c))) for a, t, c in rows
        ]

    def close(self) -> None:
        self._db.close()
