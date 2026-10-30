"""AppleMusic.all_playlist_tracks: one osascript call, JSON parsed (subprocess.run is faked)."""
from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from tune_sort.music import AppleMusic, MusicError, Track

RUN = "tune_sort.music.subprocess.run"


def recording_run(stdout: str, returncode: int = 0, stderr: str = "") -> Any:
    calls: list[Any] = []

    def run(args: Any, *a: Any, **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_parses_playlists_and_tracks(monkeypatch):
    payload = {
        "Road": [
            {"id": "A1", "name": "Schism", "artist": "Tool", "album": "Lateralus"},
            {"id": "B2", "name": "Hoppípolla", "artist": "Sigur Rós", "album": "Takk"},
        ],
        "Empty": [],
        "Bass – Drop D": [{"id": "A1", "name": "Schism", "artist": "Tool", "album": "Lateralus"}],
    }
    run = recording_run(json.dumps(payload, ensure_ascii=False))
    monkeypatch.setattr(RUN, run)
    got = AppleMusic().all_playlist_tracks()
    assert got == {
        "Road": [
            Track(persistent_id="A1", name="Schism", artist="Tool", album="Lateralus"),
            Track(persistent_id="B2", name="Hoppípolla", artist="Sigur Rós", album="Takk"),
        ],
        "Empty": [],
        "Bass – Drop D": [
            Track(persistent_id="A1", name="Schism", artist="Tool", album="Lateralus")
        ],
    }


def test_runs_osascript_exactly_once(monkeypatch):
    run = recording_run(json.dumps({"A": [], "B": [], "C": []}))
    monkeypatch.setattr(RUN, run)
    AppleMusic().all_playlist_tracks()
    assert len(run.calls) == 1


def test_empty_object_gives_empty_dict(monkeypatch):
    monkeypatch.setattr(RUN, recording_run("{}"))
    assert AppleMusic().all_playlist_tracks() == {}


def test_nonzero_exit_raises_music_error(monkeypatch):
    monkeypatch.setattr(RUN, recording_run("", returncode=1, stderr="Music got an error"))
    with pytest.raises(MusicError):
        AppleMusic().all_playlist_tracks()


@pytest.mark.parametrize("stdout", ["", "not json", '{"A": [', "\n"])
def test_bad_json_raises_music_error(monkeypatch, stdout):
    monkeypatch.setattr(RUN, recording_run(stdout))
    with pytest.raises(MusicError) as info:
        AppleMusic().all_playlist_tracks()
    assert not isinstance(info.value, json.JSONDecodeError)
