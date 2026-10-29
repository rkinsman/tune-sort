"""AppleMusic: osascript output handling (subprocess.run is faked)."""
from __future__ import annotations

import json
import subprocess

import pytest

from tune_sort.music import AppleMusic, MusicError

RUN = "tune_sort.music.subprocess.run"


def fake_run(stdout, returncode=0, stderr=""):
    def run(args, *a, **kw):
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)

    return run


def test_list_playlists_parses_json(monkeypatch):
    monkeypatch.setattr(RUN, fake_run('["A","B"]'))
    assert AppleMusic().list_playlists() == ["A", "B"]


def test_empty_stdout_raises_music_error(monkeypatch):
    monkeypatch.setattr(RUN, fake_run(""))
    with pytest.raises(MusicError):
        AppleMusic().list_playlists()


@pytest.mark.parametrize(
    "stdout",
    ["warning: something happened\n", '["A", ', "not json", "\n"],
)
def test_invalid_json_raises_music_error(monkeypatch, stdout):
    monkeypatch.setattr(RUN, fake_run(stdout))
    with pytest.raises(MusicError):
        AppleMusic().list_playlists()


def test_invalid_json_error_is_not_a_raw_decode_error(monkeypatch):
    monkeypatch.setattr(RUN, fake_run("oops"))
    with pytest.raises(MusicError) as info:
        AppleMusic().list_playlists()
    assert not isinstance(info.value, json.JSONDecodeError)
