"""Sorting a playlist's tracks into one playlist per bass tuning."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Optional

from tune_sort.cache import Cache
from tune_sort.music import Music, MusicError, Track
from tune_sort.resolver import Resolution, resolve
from tune_sort.sources import Source

Status = Literal["added", "already_present", "review", "lookup_failed", "add_error"]
OnDone = Callable[[Track, Resolution, Status, Optional[str], Optional[str]], None]


@dataclass
class Report:
    resolutions: list[tuple[Track, Resolution]] = field(default_factory=list)
    added: dict[str, list[Track]] = field(default_factory=dict)  # playlist -> tracks added
    already_present: dict[str, list[Track]] = field(default_factory=dict)
    created_playlists: list[str] = field(default_factory=list)
    review: list[Track] = field(default_factory=list)
    lookup_failed: list[Track] = field(default_factory=list)  # retried on the next sort
    add_errors: list[tuple[Track, str, str]] = field(default_factory=list)  # track, playlist, error
    cancelled: bool = False  # True if should_stop ended the sort early


def sort_playlist(
    music: Music,
    playlist: str,
    sources: Sequence[Source],
    cache: Cache,
    dry_run: bool = False,
    on_progress: Optional[Callable[[int, int, Track], None]] = None,
    recheck: bool = False,
    should_stop: Optional[Callable[[], bool]] = None,
    on_done: Optional[OnDone] = None,
) -> Report:
    """Resolve every track in `playlist` and add each resolved track to the playlist named
    by its tuning's `playlist_name`, creating that playlist if needed.

    Safe to re-run: existing playlists are reused and a track already in its target
    playlist is reported in `already_present`, not added again. Tracks needing review are
    not added anywhere. With dry_run, nothing in Music is created or changed and
    `added` lists what would be added.

    on_progress, if given, is called as on_progress(i, total, track) just before each
    track is resolved, with i counting from 1 and total the number of tracks in the
    playlist. It is not called for an empty playlist.

    Tracks whose lookup failed go in `lookup_failed`. A MusicError while adding a track is
    recorded in `add_errors` and the sort carries on. `recheck` is passed to resolve.

    should_stop, if given, is called at the top of each loop iteration, before on_progress.
    If it returns True the sort stops, the tracks not yet resolved are left alone, and
    `Report.cancelled` is True.

    on_done, if given, is called once per track, in order, after its outcome is recorded, as
    on_done(track, resolution, status, playlist, error). status is one of "added",
    "already_present", "review", "lookup_failed" or "add_error". playlist is the target for
    "added", "already_present" and "add_error", else None. error is set only for "add_error".
    """
    if should_stop is not None or on_done is not None:
        raise NotImplementedError("should_stop and on_done are not implemented yet")
    report = Report()
    tracks = music.get_tracks(playlist)
    existing = set(music.list_playlists())
    # Persistent IDs in each target playlist, loaded on first use and kept up to date.
    members: dict[str, set[str]] = {}

    for i, track in enumerate(tracks, 1):
        if on_progress is not None:
            on_progress(i, len(tracks), track)
        resolution = resolve(track.artist, track.name, sources, cache, recheck)
        report.resolutions.append((track, resolution))
        if resolution.lookup_failed:
            report.lookup_failed.append(track)
            continue
        if resolution.tuning is None:
            report.review.append(track)
            continue

        target = resolution.tuning.playlist_name
        if target not in members:
            if target in existing:
                members[target] = {t.persistent_id for t in music.get_tracks(target)}
            else:
                if not dry_run:
                    music.ensure_playlist(target)
                report.created_playlists.append(target)
                members[target] = set()

        if track.persistent_id in members[target]:
            report.already_present.setdefault(target, []).append(track)
            continue
        if not dry_run:
            try:
                music.add_track(target, track.persistent_id)
            except MusicError as e:
                report.add_errors.append((track, target, str(e)))
                continue
        members[target].add(track.persistent_id)
        report.added.setdefault(target, []).append(track)

    return report
