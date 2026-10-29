"""Songsterr lookup via its public search API, which lists every track's tuning."""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urlencode

from tune_sort import matching
from tune_sort.sources import Fetch, FetchError, Match
from tune_sort.tuning import Tuning, from_midi

SEARCH_URL = "https://www.songsterr.com/api/songs"
SONG_URL = "https://www.songsterr.com/a/wa/song?id={}"
BASS_INSTRUMENT_IDS = range(32, 40)  # General MIDI basses


def search_url(artist: str, title: str) -> str:
    """URL of the Songsterr search for "<artist> <title>"."""
    return SEARCH_URL + "?" + urlencode({"pattern": f"{artist} {title}", "size": 10})


def _is_bass(track: Any) -> bool:
    return isinstance(track, dict) and track.get("instrumentId") in BASS_INSTRUMENT_IDS


def _bass_tuning(song: dict[str, Any]) -> Optional[Tuning]:
    tracks = song.get("tracks") or []
    popular = song.get("popularTrackBass")
    bass = None
    if isinstance(popular, int) and 0 <= popular < len(tracks) and _is_bass(tracks[popular]):
        bass = tracks[popular]
    else:
        bass = next((t for t in tracks if _is_bass(t)), None)
    if bass is None:
        return None
    try:
        return from_midi(reversed(list(bass["tuning"])))  # Songsterr lists highest first
    except (KeyError, TypeError, ValueError):
        return None


class Songsterr:
    name = "songsterr"

    def __init__(self, fetch: Fetch) -> None:
        self._fetch = fetch

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        try:
            songs = json.loads(self._fetch(search_url(artist, title)))
        except (FetchError, ValueError):
            return None
        if not isinstance(songs, list):
            return None
        candidates = [s for s in songs if isinstance(s, dict) and not s.get("isJunk")]
        for exact, test in ((True, matching.is_exact), (False, matching.is_similar)):
            for song in candidates:
                other_artist, other_title = str(song.get("artist", "")), str(song.get("title", ""))
                if not test(artist, title, other_artist, other_title):
                    continue
                tuning = _bass_tuning(song)
                if tuning is not None:
                    return Match(
                        tuning=tuning,
                        source="songsterr",
                        url=SONG_URL.format(song.get("songId")),
                        matched_artist=other_artist,
                        matched_title=other_title,
                        exact=exact,
                    )
        return None
