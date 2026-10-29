"""Songsterr lookup via its public search API, which lists every track's tuning.

For bass the track is tracks[popularTrackBass] when that is a bass (instrumentId 32-39),
else the first bass track. For guitar it is tracks[popularTrackGuitar] when that is a
guitar (instrumentId 24-31), else the first guitar track.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urlencode

from tune_sort import matching
from tune_sort.sources import Fetch, FetchError, Match
from tune_sort.tuning import Instrument, Tuning, from_midi

SEARCH_URL = "https://www.songsterr.com/api/songs"
SONG_URL = "https://www.songsterr.com/a/wa/song?id={}"
BASS_INSTRUMENT_IDS = range(32, 40)  # General MIDI basses
GUITAR_INSTRUMENT_IDS = range(24, 32)  # General MIDI guitars
_TRACKS = {
    "bass": ("popularTrackBass", BASS_INSTRUMENT_IDS),
    "guitar": ("popularTrackGuitar", GUITAR_INSTRUMENT_IDS),
}


def search_url(artist: str, title: str) -> str:
    """URL of the Songsterr search for "<artist> <title>"."""
    return SEARCH_URL + "?" + urlencode({"pattern": f"{artist} {title}", "size": 10})


def _track_tuning(song: dict[str, Any], instrument: Instrument) -> Optional[Tuning]:
    popular_key, ids = _TRACKS[instrument]

    def is_instrument(track: Any) -> bool:
        return isinstance(track, dict) and track.get("instrumentId") in ids

    tracks = song.get("tracks") or []
    popular = song.get(popular_key)
    if isinstance(popular, int) and 0 <= popular < len(tracks) and is_instrument(tracks[popular]):
        track = tracks[popular]
    else:
        track = next((t for t in tracks if is_instrument(t)), None)
    if track is None:
        return None
    try:
        # Songsterr lists the highest string first.
        return from_midi(reversed(list(track["tuning"])), instrument)
    except (KeyError, TypeError, ValueError):
        return None


class Songsterr:
    name = "songsterr"

    def __init__(self, fetch: Fetch, instrument: Instrument = "bass") -> None:
        self._fetch = fetch
        self.instrument: Instrument = instrument

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
                tuning = _track_tuning(song, self.instrument)
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
