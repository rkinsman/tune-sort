"""tune_sort.wire: plain-dict encoders for the serve protocol."""
from __future__ import annotations

import json

from tests.conftest import FakeMusic, FakeSource, T, make_match, make_track
from tune_sort.cache import CachedSong, Entry
from tune_sort.sorter import TrackState, sort_playlist
from tune_sort.sources import SourceError
from tune_sort.wire import (
    cached_song_json,
    match_json,
    report_json,
    track_json,
    track_state_json,
    tuning_json,
)

DASH = "–"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH

DROP_D_JSON = {"name": "Drop D", "playlist_name": DROP_D, "notes": "D A D G"}


def test_tuning_json_bass():
    assert tuning_json(T("D A D G")) == DROP_D_JSON


def test_tuning_json_uses_en_dash():
    assert tuning_json(T("D A D G"))["playlist_name"] == "Bass – Drop D"


def test_tuning_json_guitar():
    assert tuning_json(T("D A D G B E", "guitar")) == {
        "name": "Drop D",
        "playlist_name": "Guitar %s Drop D" % DASH,
        "notes": "D A D G B E",
    }


def test_track_json_maps_name_to_title():
    t = make_track("PID1", "Tool", "Schism")
    assert track_json(t) == {"artist": "Tool", "title": "Schism", "persistent_id": "PID1"}


def test_track_json_keeps_unicode():
    t = make_track("P", "Sigur Rós", "Hoppípolla")
    assert track_json(t) == {"artist": "Sigur Rós", "title": "Hoppípolla", "persistent_id": "P"}


def test_match_json():
    m = make_match("D A D G", "ug-bass", exact=False, artist="Tool", title="Schism")
    assert match_json(m) == {
        "tuning": DROP_D_JSON,
        "source": "ug-bass",
        "url": "https://example.test/ug-bass",
        "matched_artist": "Tool",
        "matched_title": "Schism",
        "exact": False,
    }


def test_cached_song_json():
    song = CachedSong("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    assert cached_song_json(song) == {
        "artist": "Tool",
        "title": "Schism",
        "tuning": DROP_D_JSON,
        "source": "manual",
        "confirmed": True,
    }


def test_track_state_json_cached():
    t = make_track("1", "Tool", "Schism")
    state = TrackState(t, Entry(T("D A D G"), "ug-bass", False), None)
    assert track_state_json(state) == {
        "artist": "Tool",
        "title": "Schism",
        "persistent_id": "1",
        "state": "cached",
        "tuning": DROP_D_JSON,
        "source": "ug-bass",
        "confirmed": False,
    }


def test_track_state_json_review():
    t = make_track("2", "Opeth", "Deliverance")
    m = make_match("D A D G", artist="Opeth", title="Deliverance")
    got = track_state_json(TrackState(t, None, (m,)))
    assert got == {
        "artist": "Opeth",
        "title": "Deliverance",
        "persistent_id": "2",
        "state": "review",
        "candidates": [match_json(m)],
    }
    assert got["candidates"][0]["tuning"] == DROP_D_JSON


def test_track_state_json_review_without_candidates():
    t = make_track("2", "Opeth", "Deliverance")
    got = track_state_json(TrackState(t, None, ()))
    assert got["state"] == "review"
    assert got["candidates"] == []


def test_track_state_json_unknown():
    t = make_track("3", "Rush", "YYZ")
    assert track_state_json(TrackState(t, None, None)) == {
        "artist": "Rush",
        "title": "YYZ",
        "persistent_id": "3",
        "state": "unknown",
    }


def test_report_json_dry_run(cache):
    a = make_track("A", "Tool", "Schism")
    u = make_track("U", "Nobody", "Nothing")
    f = make_track("F", "Rush", "YYZ")
    src = FakeSource(
        "s",
        {
            ("Tool", "Schism"): make_match("D A D G"),
            ("Rush", "YYZ"): SourceError("down"),
        },
    )
    music = FakeMusic({"P": [a, u, f]})
    report = sort_playlist(music, "P", [src], cache, dry_run=True)
    got = report_json(report)
    assert got["cancelled"] is False
    assert got["added"] == {DROP_D: [track_json(a)]}
    assert got["already_present"] == {}
    assert got["review"] == [track_json(u)]
    assert got["lookup_failed"] == [track_json(f)]
    assert got["add_errors"] == []
    assert set(got) == {
        "cancelled",
        "created_playlists",
        "added",
        "already_present",
        "review",
        "lookup_failed",
        "add_errors",
    }
    assert music.add_calls == []
    json.dumps(got)  # plain JSON-serialisable data


def test_report_json_already_present_and_add_errors(cache):
    a = make_track("A", "Tool", "Schism")
    b = make_track("B", "Opeth", "Deliverance")
    src = FakeSource(
        "s",
        {
            ("Tool", "Schism"): make_match("D A D G"),
            ("Opeth", "Deliverance"): make_match("D# G# C# F#"),
        },
    )
    music = FakeMusic({"P": [a, b], DROP_D: [a]}, fail_add={"B": "boom"})
    got = report_json(sort_playlist(music, "P", [src], cache))
    assert got["already_present"] == {DROP_D: [track_json(a)]}
    assert got["added"] == {}
    assert got["add_errors"] == [
        {"track": track_json(b), "playlist": EB_STD, "error": "boom"}
    ]
    assert sorted(got["created_playlists"]) == [EB_STD]
    json.dumps(got)


def test_report_json_cancelled(cache):
    a = make_track("A", "Tool", "Schism")
    music = FakeMusic({"P": [a]})
    report = sort_playlist(music, "P", [FakeSource("s")], cache, should_stop=lambda: True)
    got = report_json(report)
    assert got["cancelled"] is True
    assert got["added"] == {}
