"""sorter.track_states and TrackState.state."""
from __future__ import annotations

import pytest

from tests.conftest import FakeMusic, T, make_match, make_track
from tune_sort.cache import Entry
from tune_sort.music import MusicError
from tune_sort.sorter import TrackState, track_states

PL = "Songs"


def test_states_cached_review_unknown(cache):
    t1 = make_track("1", "Tool", "Schism")
    t2 = make_track("2", "Opeth", "Deliverance")
    t3 = make_track("3", "Mastodon", "Blood and Thunder")
    music = FakeMusic({PL: [t1, t2, t3]})
    entry = Entry(T("D A D G"), "ug-bass", True)
    cands = [make_match("C G C F", artist="Opeth", title="Deliverance")]
    cache.put("Tool", "Schism", entry)
    cache.add_review("Opeth", "Deliverance", cands)

    states = track_states(music, PL, cache)

    assert [s.track for s in states] == [t1, t2, t3]
    assert [s.state for s in states] == ["cached", "review", "unknown"]
    assert states[0].entry == entry
    assert states[0].candidates is None
    assert states[1].entry is None
    assert states[1].candidates == tuple(cands)
    assert states[2].entry is None
    assert states[2].candidates is None


def test_states_order_follows_playlist(cache):
    tracks = [make_track(str(i), "Artist%d" % i, "Song%d" % i) for i in (5, 3, 9, 1)]
    cache.put("Artist3", "Song3", Entry(T("E A D G"), "manual", True))
    states = track_states(FakeMusic({PL: tracks}), PL, cache)
    assert [s.track.persistent_id for s in states] == ["5", "3", "9", "1"]
    assert [s.state for s in states] == ["unknown", "cached", "unknown", "unknown"]


def test_states_empty_playlist(cache):
    assert track_states(FakeMusic({PL: []}), PL, cache) == []


def test_states_missing_playlist_raises_music_error(cache):
    with pytest.raises(MusicError):
        track_states(FakeMusic({PL: []}), "Nope", cache)


def test_review_candidates_may_be_empty(cache):
    t = make_track("1", "Tool", "Schism")
    cache.add_review("Tool", "Schism", [])
    (s,) = track_states(FakeMusic({PL: [t]}), PL, cache)
    assert s.state == "review"
    assert s.candidates == ()
    assert s.entry is None


def test_trackstate_state_property():
    t = make_track("1", "Tool", "Schism")
    entry = Entry(T("D A D G"), "ug-bass", False)
    assert TrackState(t, entry, None).state == "cached"
    assert TrackState(t, entry, ()).state == "cached"
    assert TrackState(t, None, ()).state == "review"
    assert TrackState(t, None, (make_match("D A D G"),)).state == "review"
    assert TrackState(t, None, None).state == "unknown"
