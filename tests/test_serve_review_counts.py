"""serve: the review_counts command."""
from __future__ import annotations

from typing import Dict, List

import pytest

from tests.conftest import FakeMusic, make_track
from tests.test_serve import one, req, result, run, seed
from tune_sort.music import MusicError, Track

D = "–"

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")


class BrokenMusic(FakeMusic):
    def all_playlist_tracks(self) -> Dict[str, List[Track]]:
        raise MusicError("Music is not running")


def queue(tmp_path, instrument, *pairs):
    c = seed(tmp_path, instrument)
    for artist, title in pairs:
        c.add_review(artist, title, [])
    c.close()


def test_review_counts_result(tmp_path):
    queue(tmp_path, "bass", ("Tool", "Schism"), ("Opeth", "Deliverance"))
    music = FakeMusic({"Road": [A, B, C], "Chill": [B], "Other": [C], "Bass %s Drop D" % D: [A]})
    got = result(tmp_path, req(1, "review_counts", instrument="bass"), music=music)
    assert got == {"Road": 2, "Chill": 1}


def test_review_counts_empty(tmp_path):
    got = result(tmp_path, req(1, "review_counts", instrument="bass"), music=FakeMusic({"P": [A]}))
    assert got == {}


def test_review_counts_is_per_instrument(tmp_path):
    queue(tmp_path, "guitar", ("Tool", "Schism"))
    music = FakeMusic({"Road": [A], "Guitar %s Drop D" % D: [A]})
    assert result(tmp_path, req(1, "review_counts", instrument="bass"), music=music) == {}
    got = result(tmp_path, req(2, "review_counts", instrument="guitar"), music=music)
    assert got == {"Road": 1}


def test_review_counts_reply_id(tmp_path):
    (reply,) = run(tmp_path, [req(11, "review_counts", instrument="bass")])
    assert reply == {"id": 11, "result": {}}


@pytest.mark.parametrize(
    "request_",
    [
        {"id": 1, "cmd": "review_counts"},
        {"id": 1, "cmd": "review_counts", "args": {}},
        {"id": 1, "cmd": "review_counts", "args": {"instrument": "banjo"}},
        {"id": 1, "cmd": "review_counts", "args": {"instrument": 5}},
        {"id": 1, "cmd": "review_counts", "args": {"instrument": None}},
    ],
)
def test_bad_instrument_is_bad_request(tmp_path, request_):
    reply = one(tmp_path, request_)
    assert reply["id"] == 1
    assert reply["error"]["kind"] == "bad_request"


def test_music_error_kind(tmp_path):
    reply = one(tmp_path, req(4, "review_counts", instrument="bass"), music=BrokenMusic({}))
    assert reply["id"] == 4
    assert reply["error"]["kind"] == "music"
    assert "not running" in reply["error"]["message"]
