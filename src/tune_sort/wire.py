"""Plain-dict encoders for the serve protocol's data shapes (see the mac-app spec).

The results are JSON-ready (str, bool, list, dict); text is kept as is, not escaped.
"""

from __future__ import annotations

from typing import Any

from tune_sort.cache import CachedSong
from tune_sort.music import Track
from tune_sort.sorter import Report, TrackState
from tune_sort.sources import Match
from tune_sort.tuning import Tuning


def tuning_json(tuning: Tuning) -> dict[str, Any]:
    """`{"name", "playlist_name", "notes"}`."""
    raise NotImplementedError


def track_json(track: Track) -> dict[str, Any]:
    """`{"artist", "title", "persistent_id"}`; the track's name is the title."""
    raise NotImplementedError


def match_json(match: Match) -> dict[str, Any]:
    """`{"tuning", "source", "url", "matched_artist", "matched_title", "exact"}`."""
    raise NotImplementedError


def cached_song_json(song: CachedSong) -> dict[str, Any]:
    """`{"artist", "title", "tuning", "source", "confirmed"}` with `tuning` a tuning dict."""
    raise NotImplementedError


def track_state_json(state: TrackState) -> dict[str, Any]:
    """The track dict plus `"state"`: `"cached"` adds `tuning`, `source`, `confirmed`;
    `"review"` adds `candidates` (match dicts); `"unknown"` adds nothing."""
    raise NotImplementedError


def report_json(report: Report) -> dict[str, Any]:
    """`{"cancelled", "created_playlists", "added": {playlist: [track]},
    "already_present": {playlist: [track]}, "review": [track], "lookup_failed": [track],
    "add_errors": [{"track", "playlist", "error"}]}`."""
    raise NotImplementedError
