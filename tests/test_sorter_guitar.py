from __future__ import annotations

from conftest import FakeMusic, FakeSource, make_match, make_track

from tune_sort.sorter import sort_playlist

DASH = "–"

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")


def test_guitar_sort_uses_guitar_playlists(guitar_cache):
    sources = [
        FakeSource(
            "gs",
            {
                ("Tool", "Schism"): make_match("D A D G B E", "ug-pro", instrument="guitar"),
                ("Opeth", "Deliverance"): make_match(
                    "B E A D G B E", "songsterr", instrument="guitar"
                ),
                ("Rush", "YYZ"): make_match("E A D G B E", "ug-tab", instrument="guitar"),
            },
        )
    ]
    music = FakeMusic({"P": [A, B, C]})
    report = sort_playlist(music, "P", sources, guitar_cache)
    drop_d = "Guitar %s Drop D" % DASH
    seven = "Guitar 7-String %s B Standard" % DASH
    standard = "Guitar %s E Standard" % DASH
    assert report.added == {drop_d: [A], seven: [B], standard: [C]}
    assert music.playlists[drop_d] == [A]
    assert music.playlists[seven] == [B]
    assert music.playlists[standard] == [C]
    assert not any(name.startswith("Bass") for name in music.playlists)
