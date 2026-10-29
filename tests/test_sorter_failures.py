"""sort_playlist: lookup failures, add errors, queued songs and recheck."""
from __future__ import annotations

from tests.conftest import FakeMusic, FakeSource, failing_source, make_match, make_track
from tune_sort.sorter import sort_playlist
from tune_sort.sources import SourceError

DASH = "–"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")
U = make_track("U", "Nobody", "Nothing")

ANSWERS = {
    ("Tool", "Schism"): make_match("D A D G"),
    ("Opeth", "Deliverance"): make_match("D# G# C# F#"),
    ("Rush", "YYZ"): make_match("D A D G"),
}


def src():
    return FakeSource("s", ANSWERS)


# --------------------------------------------------------------- lookup failures


def test_report_has_empty_new_fields_by_default(cache):
    report = sort_playlist(FakeMusic({"P": [A]}), "P", [src()], cache)
    assert report.lookup_failed == []
    assert report.add_errors == []


def test_lookup_failed_tracks_collected_and_not_added_or_reviewed(cache):
    s = FakeSource("s", {**ANSWERS, ("Opeth", "Deliverance"): SourceError("down")})
    music = FakeMusic({"P": [A, B, C]})
    report = sort_playlist(music, "P", [s], cache)
    assert report.lookup_failed == [B]
    assert report.review == []
    assert report.added == {DROP_D: [A, C]}
    assert all(pid != "B" for _, pid in music.add_calls)
    assert EB_STD not in music.playlists
    res = {t.persistent_id: r for t, r in report.resolutions}
    assert res["B"].lookup_failed is True
    assert res["B"].failed == ("s",)


def test_lookup_failed_and_review_are_separate_lists(cache):
    s = FakeSource("s", {**ANSWERS, ("Opeth", "Deliverance"): SourceError("down")})
    report = sort_playlist(FakeMusic({"P": [A, B, U]}), "P", [s], cache)
    assert report.lookup_failed == [B]
    assert report.review == [U]


def test_lookup_failed_songs_are_retried_next_sort(cache):
    music = FakeMusic({"P": [A, B]})
    failing = FakeSource("s", {**ANSWERS, ("Opeth", "Deliverance"): SourceError("down")})
    r1 = sort_playlist(music, "P", [failing], cache)
    assert r1.lookup_failed == [B]
    r2 = sort_playlist(music, "P", [src()], cache)
    assert r2.lookup_failed == []
    assert r2.review == []
    assert music.playlists[EB_STD] == [B]


def test_all_sources_failing(cache):
    music = FakeMusic({"P": [A, B]})
    report = sort_playlist(music, "P", [failing_source("x"), failing_source("y")], cache)
    assert report.lookup_failed == [A, B]
    assert report.review == []
    assert not any(report.added.values())
    assert music.add_calls == []
    assert [r.failed for _, r in report.resolutions] == [("x", "y"), ("x", "y")]


# ------------------------------------------------------------------- add errors


def test_add_error_recorded_and_sort_continues(cache):
    music = FakeMusic({"P": [A, B, C]}, fail_add={"B": "boom"})
    report = sort_playlist(music, "P", [src()], cache)
    assert report.add_errors == [(B, EB_STD, "boom")]
    assert B not in report.added.get(EB_STD, [])
    assert report.added == {DROP_D: [A, C]}
    assert music.playlists[DROP_D] == [A, C]
    assert report.review == []
    assert report.lookup_failed == []


def test_add_error_for_first_track_still_adds_rest(cache):
    music = FakeMusic({"P": [A, C]}, fail_add={"A": "denied"})
    report = sort_playlist(music, "P", [src()], cache)
    assert report.add_errors == [(A, DROP_D, "denied")]
    assert report.added == {DROP_D: [C]}
    assert music.playlists[DROP_D] == [C]


def test_multiple_add_errors_in_playlist_order(cache):
    music = FakeMusic({"P": [A, B, C]}, fail_add={"C": "c failed", "A": "a failed"})
    report = sort_playlist(music, "P", [src()], cache)
    assert report.add_errors == [(A, DROP_D, "a failed"), (C, DROP_D, "c failed")]
    assert not report.added.get(DROP_D)
    assert report.added.get(EB_STD) == [B]


def test_no_add_errors_in_dry_run(cache):
    music = FakeMusic({"P": [A, B]}, fail_add={"B": "boom"})
    report = sort_playlist(music, "P", [src()], cache, dry_run=True)
    assert report.add_errors == []
    assert music.add_calls == []


# -------------------------------------------------------- queued songs and recheck


def test_queued_song_not_looked_up_but_reported_for_review(cache):
    cache.add_review("Nobody", "Nothing", [])
    s = FakeSource("s", default=make_match("D A D G"))
    report = sort_playlist(FakeMusic({"P": [U]}), "P", [s], cache)
    assert s.calls == []
    assert report.review == [U]
    assert report.lookup_failed == []


def test_recheck_flag_is_passed_through(cache):
    cache.add_review("Nobody", "Nothing", [])
    s = FakeSource("s", default=make_match("D A D G"))
    music = FakeMusic({"P": [U]})
    report = sort_playlist(music, "P", [s], cache, recheck=True)
    assert s.calls == [("Nobody", "Nothing")]
    assert report.review == []
    assert music.playlists[DROP_D] == [U]
    assert cache.queued("Nobody", "Nothing") is None


def test_recheck_default_is_false(cache):
    cache.add_review("Tool", "Schism", [])
    s = src()
    report = sort_playlist(FakeMusic({"P": [A]}), "P", [s], cache)
    assert s.calls == []
    assert report.review == [A]
