from __future__ import annotations

import pytest
from conftest import FakeMusic, FakeSource, make_match, make_track

from tune_sort.cache import Entry
from tune_sort.music import MusicError
from tune_sort.sorter import sort_playlist
from tune_sort.tuning import Tuning

DASH = "–"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH
B5 = "Bass 5-String %s B Standard" % DASH
E_STD = "Bass %s E Standard" % DASH

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")
D = make_track("D", "Muse", "Hysteria")


def sources():
    return [
        FakeSource(
            "s",
            {
                ("Tool", "Schism"): make_match("D A D G"),
                ("Opeth", "Deliverance"): make_match("D# G# C# F#"),
                ("Rush", "YYZ"): make_match("B E A D G"),
                ("Muse", "Hysteria"): make_match("Eb Ab Db Gb"),
            },
        )
    ]


def test_basic_sort(cache):
    music = FakeMusic({"P": [A, B, C]})
    report = sort_playlist(music, "P", sources(), cache)
    assert music.playlists[DROP_D] == [A]
    assert music.playlists[EB_STD] == [B]
    assert music.playlists[B5] == [C]
    assert report.added == {DROP_D: [A], EB_STD: [B], B5: [C]}
    assert sorted(report.created_playlists) == sorted([DROP_D, EB_STD, B5])
    assert report.already_present == {} or all(not v for v in report.already_present.values())
    assert report.review == []


def test_enharmonic_spellings_share_playlist(cache):
    music = FakeMusic({"P": [B, D]})
    report = sort_playlist(music, "P", sources(), cache)
    assert report.added == {EB_STD: [B, D]}
    assert report.created_playlists == [EB_STD]


def test_resolutions_keep_playlist_order(cache):
    music = FakeMusic({"P": [C, A, B]})
    report = sort_playlist(music, "P", sources(), cache)
    assert [t for t, _ in report.resolutions] == [C, A, B]
    assert [r.title for _, r in report.resolutions] == ["YYZ", "Schism", "Deliverance"]


def test_rerun_adds_nothing(cache):
    music = FakeMusic({"P": [A, B, C]})
    sort_playlist(music, "P", sources(), cache)
    report = sort_playlist(music, "P", sources(), cache)
    assert not any(report.added.values())
    assert report.created_playlists == []
    present = [t for tracks in report.already_present.values() for t in tracks]
    assert sorted(t.persistent_id for t in present) == ["A", "B", "C"]
    assert report.already_present[DROP_D] == [A]


def test_new_song_added_to_existing_playlist(cache):
    music = FakeMusic({"P": [A, B]})
    sort_playlist(music, "P", sources(), cache)
    music.library[D.persistent_id] = D
    music.playlists["P"].append(D)
    report = sort_playlist(music, "P", sources(), cache)
    assert report.added == {EB_STD: [D]}
    assert report.created_playlists == []
    assert [t.persistent_id for t in music.playlists[EB_STD]] == ["B", "D"]
    assert [t for t in report.already_present.get(DROP_D, [])] == [A]


def test_duplicate_persistent_id_added_once(cache):
    music = FakeMusic({"P": [A, A]})
    report = sort_playlist(music, "P", sources(), cache)
    assert music.playlists[DROP_D] == [A]
    assert report.added == {DROP_D: [A]}


def test_review_tracks_not_added(cache):
    unknown = make_track("U", "Nobody", "Nothing")
    music = FakeMusic({"P": [A, unknown]})
    report = sort_playlist(music, "P", sources(), cache)
    assert report.review == [unknown]
    assert set(music.playlists) == {"P", DROP_D}
    assert all(pid != "U" for _, pid in music.add_calls)
    assert report.resolutions[1][1].needs_review is True


def test_dry_run_does_not_change_music(cache):
    music = FakeMusic({"P": [A, B]})
    report = sort_playlist(music, "P", sources(), cache, dry_run=True)
    assert music.ensure_calls == []
    assert music.add_calls == []
    assert list(music.playlists) == ["P"]
    assert report.added == {DROP_D: [A], EB_STD: [B]}
    assert sorted(report.created_playlists) == sorted([DROP_D, EB_STD])


def test_dry_run_with_existing_playlist_not_listed_as_created(cache):
    music = FakeMusic({"P": [A], DROP_D: []})
    report = sort_playlist(music, "P", sources(), cache, dry_run=True)
    assert report.created_playlists == []
    assert report.added == {DROP_D: [A]}
    assert music.add_calls == []


def test_dry_run_reports_already_present(cache):
    music = FakeMusic({"P": [A], DROP_D: [A]})
    report = sort_playlist(music, "P", sources(), cache, dry_run=True)
    assert report.already_present == {DROP_D: [A]}
    assert not any(report.added.values())


def test_empty_playlist(cache):
    music = FakeMusic({"P": []})
    report = sort_playlist(music, "P", sources(), cache)
    assert report.resolutions == []
    assert not any(report.added.values())
    assert not any(report.already_present.values())
    assert report.created_playlists == []
    assert report.review == []
    assert list(music.playlists) == ["P"]


def test_missing_playlist_raises(cache):
    with pytest.raises(MusicError):
        sort_playlist(FakeMusic({}), "nope", sources(), cache)


def test_old_cached_guitar_tuning_sorts_to_four_string_playlist(cache):
    # Entry saved by an older version with the full 6-string guitar tuning.
    cache.put("Tool", "Schism", Entry(Tuning((4, 9, 2, 7, 11, 4)), "ug-bass", False))
    music = FakeMusic({"P": [A]})
    report = sort_playlist(music, "P", [FakeSource("s")], cache)
    assert music.playlists[E_STD] == [A]
    assert report.added == {E_STD: [A]}
    assert not any("6-String" in name for name in music.playlists)
    assert not any("6-String" in name for name in report.added)


# ------------------------------------------------------------- on_progress callback


def test_on_progress_called_per_track_in_order(cache):
    music = FakeMusic({"P": [C, A, B]})
    calls = []
    sort_playlist(music, "P", sources(), cache, on_progress=lambda i, n, t: calls.append((i, n, t)))
    assert calls == [(1, 3, C), (2, 3, A), (3, 3, B)]


def test_on_progress_called_for_duplicates(cache):
    music = FakeMusic({"P": [A, A, B]})
    calls = []
    sort_playlist(music, "P", sources(), cache, on_progress=lambda i, n, t: calls.append((i, n, t)))
    assert calls == [(1, 3, A), (2, 3, A), (3, 3, B)]


def test_on_progress_not_called_for_empty_playlist(cache):
    music = FakeMusic({"P": []})
    calls = []
    report = sort_playlist(
        music, "P", sources(), cache, on_progress=lambda i, n, t: calls.append((i, n, t))
    )
    assert calls == []
    assert report.resolutions == []


def test_on_progress_called_before_lookup(cache):
    music = FakeMusic({"P": [A, B, C]})
    srcs = sources()
    seen = []

    def cb(i, n, t):
        seen.append((i, len(srcs[0].calls)))

    sort_playlist(music, "P", srcs, cache, on_progress=cb)
    assert seen == [(1, 0), (2, 1), (3, 2)]
    assert srcs[0].calls == [("Tool", "Schism"), ("Opeth", "Deliverance"), ("Rush", "YYZ")]


def test_on_progress_called_for_cached_tracks(cache):
    cache.put("Tool", "Schism", Entry(Tuning((2, 9, 2, 7)), "manual", True))
    music = FakeMusic({"P": [A, B]})
    srcs = sources()
    seen = []
    sort_playlist(
        music, "P", srcs, cache, on_progress=lambda i, n, t: seen.append((i, n, t.persistent_id))
    )
    assert seen == [(1, 2, "A"), (2, 2, "B")]
    assert srcs[0].calls == [("Opeth", "Deliverance")]


def test_on_progress_called_with_dry_run(cache):
    music = FakeMusic({"P": [A, B]})
    calls = []
    sort_playlist(
        music,
        "P",
        sources(),
        cache,
        dry_run=True,
        on_progress=lambda i, n, t: calls.append((i, n, t)),
    )
    assert calls == [(1, 2, A), (2, 2, B)]
    assert music.add_calls == []


def test_on_progress_does_not_change_report(cache, tmp_path):
    from tune_sort.cache import Cache

    plain_cache = Cache(tmp_path / "plain.db")
    try:
        r1 = sort_playlist(FakeMusic({"P": [A, B, C]}), "P", sources(), plain_cache)
    finally:
        plain_cache.close()
    r2 = sort_playlist(
        FakeMusic({"P": [A, B, C]}), "P", sources(), cache, on_progress=lambda i, n, t: None
    )
    assert r1.added == r2.added
    assert r1.created_playlists == r2.created_playlists
    assert [t for t, _ in r1.resolutions] == [t for t, _ in r2.resolutions]
