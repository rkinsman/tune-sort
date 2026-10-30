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
    return {"name": tuning.name, "playlist_name": tuning.playlist_name, "notes": tuning.notes}


def track_json(track: Track) -> dict[str, Any]:
    """`{"artist", "title", "persistent_id"}`; the track's name is the title."""
    return {"artist": track.artist, "title": track.name, "persistent_id": track.persistent_id}


def match_json(match: Match) -> dict[str, Any]:
    """`{"tuning", "source", "url", "matched_artist", "matched_title", "exact"}`."""
    return {
        "tuning": tuning_json(match.tuning),
        "source": match.source,
        "url": match.url,
        "matched_artist": match.matched_artist,
        "matched_title": match.matched_title,
        "exact": match.exact,
    }


def cached_song_json(song: CachedSong) -> dict[str, Any]:
    """`{"artist", "title", "tuning", "source", "confirmed"}` with `tuning` a tuning dict."""
    return {
        "artist": song.artist,
        "title": song.title,
        "tuning": tuning_json(song.entry.tuning),
        "source": song.entry.source,
        "confirmed": song.entry.confirmed,
    }


def track_state_json(state: TrackState) -> dict[str, Any]:
    """The track dict plus `"state"`: `"cached"` adds `tuning`, `source`, `confirmed`;
    `"review"` adds `candidates` (match dicts); `"unknown"` adds nothing."""
    out = track_json(state.track)
    out["state"] = state.state
    if state.entry is not None:
        out["tuning"] = tuning_json(state.entry.tuning)
        out["source"] = state.entry.source
        out["confirmed"] = state.entry.confirmed
    elif state.candidates is not None:
        out["candidates"] = [match_json(m) for m in state.candidates]
    return out


def report_json(report: Report) -> dict[str, Any]:
    """`{"cancelled", "created_playlists", "added": {playlist: [track]},
    "already_present": {playlist: [track]}, "review": [track], "lookup_failed": [track],
    "add_errors": [{"track", "playlist", "error"}]}`."""
    return {
        "cancelled": report.cancelled,
        "created_playlists": list(report.created_playlists),
        "added": {name: [track_json(t) for t in ts] for name, ts in report.added.items()},
        "already_present": {
            name: [track_json(t) for t in ts] for name, ts in report.already_present.items()
        },
        "review": [track_json(t) for t in report.review],
        "lookup_failed": [track_json(t) for t in report.lookup_failed],
        "add_errors": [
            {"track": track_json(t), "playlist": name, "error": error}
            for t, name, error in report.add_errors
        ],
    }
