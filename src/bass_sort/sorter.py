"""Sorting a playlist's tracks into one playlist per bass tuning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from bass_sort.cache import Cache
from bass_sort.music import Music, Track
from bass_sort.resolver import Resolution, resolve
from bass_sort.sources import Source


@dataclass
class Report:
    resolutions: list[tuple[Track, Resolution]] = field(default_factory=list)
    added: dict[str, list[Track]] = field(default_factory=dict)  # playlist -> tracks added
    already_present: dict[str, list[Track]] = field(default_factory=dict)
    created_playlists: list[str] = field(default_factory=list)
    review: list[Track] = field(default_factory=list)


def sort_playlist(
    music: Music,
    playlist: str,
    sources: Sequence[Source],
    cache: Cache,
    dry_run: bool = False,
) -> Report:
    """Resolve every track in `playlist` and add each resolved track to the playlist named
    by its tuning's `playlist_name`, creating that playlist if needed.

    Safe to re-run: existing playlists are reused and a track already in its target
    playlist is reported in `already_present`, not added again. Tracks needing review are
    not added anywhere. With dry_run, nothing in Music is created or changed and
    `added` lists what would be added.
    """
    report = Report()
    tracks = music.get_tracks(playlist)
    existing = set(music.list_playlists())
    # Persistent IDs in each target playlist, loaded on first use and kept up to date.
    members: dict[str, set[str]] = {}

    for track in tracks:
        resolution = resolve(track.artist, track.name, sources, cache)
        report.resolutions.append((track, resolution))
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
            music.add_track(target, track.persistent_id)
        members[target].add(track.persistent_id)
        report.added.setdefault(target, []).append(track)

    return report
