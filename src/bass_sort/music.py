"""Reading and writing playlists in the macOS Music app."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Track:
    persistent_id: str
    name: str
    artist: str
    album: str


class MusicError(Exception):
    pass


class Music(Protocol):
    def list_playlists(self) -> list[str]:
        """Names of the user's playlists."""
        ...

    def get_tracks(self, playlist: str) -> list[Track]:
        """Tracks in a playlist, in order. Raises MusicError if it doesn't exist."""
        ...

    def ensure_playlist(self, name: str) -> bool:
        """Create the playlist if missing. Returns True if it was created."""
        ...

    def add_track(self, playlist: str, persistent_id: str) -> bool:
        """Add a track to a playlist unless it is already there.
        Returns True if added, False if it was already there."""
        ...


class AppleMusic:
    """Music implemented with JXA scripts run through `osascript -l JavaScript`."""

    def list_playlists(self) -> list[str]:
        return list(_run_jxa(_LIST_PLAYLISTS))

    def get_tracks(self, playlist: str) -> list[Track]:
        rows = _run_jxa(_GET_TRACKS, playlist)
        return [Track(r["id"], r["name"], r["artist"], r["album"]) for r in rows]

    def ensure_playlist(self, name: str) -> bool:
        return bool(_run_jxa(_ENSURE_PLAYLIST, name))

    def add_track(self, playlist: str, persistent_id: str) -> bool:
        return bool(_run_jxa(_ADD_TRACK, playlist, persistent_id))


# Each script's run(argv) returns JSON; a thrown Error becomes a MusicError.
_PRELUDE = """
const app = Application("Music");
function playlist(name) {
  const found = app.userPlaylists.whose({name: name})();
  if (found.length === 0) throw new Error("No playlist named " + JSON.stringify(name));
  return found[0];
}
"""

_LIST_PLAYLISTS = """
function run(argv) { return JSON.stringify(app.userPlaylists.name()); }
"""

_GET_TRACKS = """
function run(argv) {
  const tracks = playlist(argv[0]).tracks;
  const ids = tracks.persistentID(), names = tracks.name(),
        artists = tracks.artist(), albums = tracks.album();
  return JSON.stringify(ids.map((id, i) =>
    ({id: id, name: names[i], artist: artists[i], album: albums[i]})));
}
"""

_ENSURE_PLAYLIST = """
function run(argv) {
  if (app.userPlaylists.whose({name: argv[0]})().length > 0) return "false";
  app.make({new: "userPlaylist", withProperties: {name: argv[0]}});
  return "true";
}
"""

_ADD_TRACK = """
function run(argv) {
  const target = playlist(argv[0]);
  if (target.tracks.whose({persistentID: argv[1]})().length > 0) return "false";
  const found = app.libraryPlaylists[0].tracks.whose({persistentID: argv[1]})();
  if (found.length === 0) throw new Error("Track " + argv[1] + " is not in your library");
  app.duplicate(found[0], {to: target});
  return "true";
}
"""


def _run_jxa(script: str, *args: str) -> Any:
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", "-", *args],
            input=_PRELUDE + script,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MusicError(f"couldn't run osascript: {e}") from e
    if proc.returncode != 0:
        message = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "unknown"
        raise MusicError(message)
    return json.loads(proc.stdout)
