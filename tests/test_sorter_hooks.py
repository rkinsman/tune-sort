"""sort_playlist: should_stop cancellation and on_done per-track notifications."""
from __future__ import annotations

from tests.conftest import FakeMusic, FakeSource, make_match, make_track
from tune_sort.sorter import sort_playlist
from tune_sort.sources import SourceError

DASH = "–"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")
D = make_track("D", "Muse", "Hysteria")
U = make_track("U", "Nobody", "Nothing")

ANSWERS = {
    ("Tool", "Schism"): make_match("D A D G"),
    ("Opeth", "Deliverance"): make_match("D# G# C# F#"),
    ("Rush", "YYZ"): make_match("D A D G"),
    ("Muse", "Hysteria"): make_match("Eb Ab Db Gb"),
}


def src():
    return FakeSource("s", ANSWERS)


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, track, resolution, status, playlist, error):
        self.calls.append((track, resolution, status, playlist, error))

    def summary(self):
        return [(t.persistent_id, s, p, e) for t, _, s, p, e in self.calls]


# ------------------------------------------------------------------ should_stop


def test_should_stop_before_first_track(cache):
    music = FakeMusic({"P": [A, B, C, D]})
    progress = []
    report = sort_playlist(
        music,
        "P",
        [src()],
        cache,
        on_progress=lambda i, n, t: progress.append((i, n, t)),
        should_stop=lambda: True,
    )
    assert report.cancelled is True
    assert report.resolutions == []
    assert progress == []
    assert music.add_calls == []


def test_should_stop_after_two(cache):
    music = FakeMusic({"P": [A, B, C, D]})
    done = Recorder()

    # Becomes True once two tracks have been fully handled.
    def stop():
        return len(done.calls) >= 2

    report = sort_playlist(music, "P", [src()], cache, should_stop=stop, on_done=done)
    assert report.cancelled is True
    assert [t for t, _ in report.resolutions] == [A, B]
    assert report.added == {DROP_D: [A], EB_STD: [B]}
    assert music.playlists[DROP_D] == [A]
    assert music.playlists[EB_STD] == [B]
    assert sorted(music.add_calls) == sorted([(DROP_D, "A"), (EB_STD, "B")])
    assert len(done.calls) == 2


def test_should_stop_after_two_counted_by_calls(cache):
    music = FakeMusic({"P": [A, B, C, D]})
    progress = []
    checks = []

    def stop():
        checks.append(1)
        return len(checks) > 2

    report = sort_playlist(
        music,
        "P",
        [src()],
        cache,
        on_progress=lambda i, n, t: progress.append(i),
        should_stop=stop,
    )
    assert report.cancelled is True
    assert len(report.resolutions) == 2
    assert progress == [1, 2]
    assert report.added == {DROP_D: [A], EB_STD: [B]}
    assert music.playlists[DROP_D] == [A]
    assert music.playlists[EB_STD] == [B]


def test_should_stop_dry_run_makes_no_changes(cache):
    music = FakeMusic({"P": [A, B, C, D]})
    checks = []

    def stop():
        checks.append(1)
        return len(checks) > 2

    report = sort_playlist(music, "P", [src()], cache, dry_run=True, should_stop=stop)
    assert report.cancelled is True
    assert report.added == {DROP_D: [A], EB_STD: [B]}
    assert music.add_calls == []
    assert list(music.playlists) == ["P"]


def test_should_stop_always_false_completes(cache):
    music = FakeMusic({"P": [A, B, C, D]})
    report = sort_playlist(music, "P", [src()], cache, should_stop=lambda: False)
    assert report.cancelled is False
    assert len(report.resolutions) == 4
    assert report.added == {DROP_D: [A, C], EB_STD: [B, D]}


def test_not_cancelled_by_default(cache):
    music = FakeMusic({"P": [A, B]})
    report = sort_playlist(music, "P", [src()], cache)
    assert report.cancelled is False
    assert len(report.resolutions) == 2


# ----------------------------------------------------------------------- on_done


def test_on_done_called_once_per_track_in_order(cache):
    music = FakeMusic({"P": [C, A, B, D]})
    done = Recorder()
    report = sort_playlist(music, "P", [src()], cache, on_done=done)
    assert [t for t, *_ in done.calls] == [C, A, B, D]
    assert [r for _, r, *_ in done.calls] == [r for _, r in report.resolutions]


def test_on_done_called_after_progress_for_same_track(cache):
    music = FakeMusic({"P": [A, B]})
    events = []
    sort_playlist(
        music,
        "P",
        [src()],
        cache,
        on_progress=lambda i, n, t: events.append(("progress", t.persistent_id)),
        on_done=lambda t, r, s, p, e: events.append(("done", t.persistent_id)),
    )
    assert events == [("progress", "A"), ("done", "A"), ("progress", "B"), ("done", "B")]


def test_on_done_status_added_real_run(cache):
    music = FakeMusic({"P": [A]})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, on_done=done)
    assert done.summary() == [("A", "added", DROP_D, None)]
    assert music.playlists[DROP_D] == [A]


def test_on_done_status_added_dry_run(cache):
    music = FakeMusic({"P": [A]})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, dry_run=True, on_done=done)
    assert done.summary() == [("A", "added", DROP_D, None)]
    assert music.add_calls == []


def test_on_done_status_already_present(cache):
    music = FakeMusic({"P": [A], DROP_D: [A]})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, on_done=done)
    assert done.summary() == [("A", "already_present", DROP_D, None)]


def test_on_done_status_already_present_dry_run(cache):
    music = FakeMusic({"P": [A], DROP_D: [A]})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, dry_run=True, on_done=done)
    assert done.summary() == [("A", "already_present", DROP_D, None)]


def test_on_done_status_review(cache):
    music = FakeMusic({"P": [U]})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, on_done=done)
    assert done.summary() == [("U", "review", None, None)]
    assert done.calls[0][1].needs_review is True


def test_on_done_status_lookup_failed(cache):
    s = FakeSource("s", {**ANSWERS, ("Opeth", "Deliverance"): SourceError("down")})
    music = FakeMusic({"P": [B]})
    done = Recorder()
    sort_playlist(music, "P", [s], cache, on_done=done)
    assert done.summary() == [("B", "lookup_failed", None, None)]
    assert done.calls[0][1].lookup_failed is True


def test_on_done_status_add_error(cache):
    music = FakeMusic({"P": [A, B]}, fail_add={"B": "boom"})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, on_done=done)
    assert done.summary() == [
        ("A", "added", DROP_D, None),
        ("B", "add_error", EB_STD, "boom"),
    ]


def test_on_done_playlist_is_target(cache):
    music = FakeMusic({"P": [A, B, C, D, U]}, fail_add={"D": "nope"})
    done = Recorder()
    sort_playlist(music, "P", [src()], cache, on_done=done)
    assert done.summary() == [
        ("A", "added", DROP_D, None),
        ("B", "added", EB_STD, None),
        ("C", "added", DROP_D, None),
        ("D", "add_error", EB_STD, "nope"),
        ("U", "review", None, None),
    ]


def test_on_done_does_not_change_report(cache):
    music = FakeMusic({"P": [A, B, U]})
    report = sort_playlist(music, "P", [src()], cache, on_done=Recorder())
    assert report.added == {DROP_D: [A], EB_STD: [B]}
    assert report.review == [U]
    assert report.cancelled is False
