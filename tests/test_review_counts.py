"""sorter.review_counts: per-playlist counts of distinct songs queued for review."""
from __future__ import annotations

from typing import Dict, List

import pytest

from tests.conftest import FakeMusic, T, make_match, make_track
from tune_sort.cache import Cache, Entry
from tune_sort.music import MusicError, Track
from tune_sort.sorter import review_counts

D = "–"

SCHISM = make_track("1", "Tool", "Schism")
DELIV = make_track("2", "Opeth", "Deliverance")
YYZ = make_track("3", "Rush", "YYZ")


class NoGetTracksMusic(FakeMusic):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.all_calls = 0

    def get_tracks(self, playlist: str) -> List[Track]:
        raise AssertionError("get_tracks must not be called")

    def all_playlist_tracks(self) -> Dict[str, List[Track]]:
        self.all_calls += 1
        return super().all_playlist_tracks()


class BrokenMusic(FakeMusic):
    def all_playlist_tracks(self) -> Dict[str, List[Track]]:
        raise MusicError("Music is not running")


def queue(cache, *pairs):
    for artist, title in pairs:
        cache.add_review(artist, title, [make_match("D A D G", artist=artist, title=title)])


def test_counts_per_playlist(cache):
    queue(cache, ("Tool", "Schism"), ("Opeth", "Deliverance"))
    music = FakeMusic({"Road": [SCHISM, DELIV, YYZ], "Chill": [DELIV]})
    assert review_counts(music, cache) == {"Road": 2, "Chill": 1}


def test_zero_counts_left_out(cache):
    queue(cache, ("Tool", "Schism"))
    music = FakeMusic({"Road": [SCHISM], "Other": [YYZ], "Empty": []})
    assert review_counts(music, cache) == {"Road": 1}


def test_nothing_queued_gives_empty(cache):
    assert review_counts(FakeMusic({"Road": [SCHISM]}), cache) == {}


def test_no_playlists_gives_empty(cache):
    queue(cache, ("Tool", "Schism"))
    assert review_counts(FakeMusic({}), cache) == {}


def test_cached_but_not_queued_does_not_count(cache):
    cache.put("Tool", "Schism", Entry(T("D A D G"), "ug-bass", True))
    assert review_counts(FakeMusic({"Road": [SCHISM]}), cache) == {}


def test_song_in_two_playlists_counts_in_each(cache):
    queue(cache, ("Tool", "Schism"))
    music = FakeMusic({"A": [SCHISM], "B": [SCHISM, YYZ]})
    assert review_counts(music, cache) == {"A": 1, "B": 1}


def test_duplicate_within_playlist_counts_once(cache):
    queue(cache, ("Tool", "Schism"))
    dup = make_track("9", "Tool", "Schism")
    music = FakeMusic({"Road": [SCHISM, dup]})
    assert review_counts(music, cache) == {"Road": 1}


def test_differently_titled_tracks_of_one_queued_song_count_once(cache):
    queue(cache, ("Tool", "Schism"))
    remaster = make_track("7", "tool", "Schism (Remastered)")
    music = FakeMusic({"Road": [SCHISM, remaster]})
    assert review_counts(music, cache) == {"Road": 1}


def test_whole_library_count_equals_queued_songs_present_despite_duplicates(cache):
    queue(cache, ("Tool", "Schism"), ("Opeth", "Deliverance"), ("Nobody", "Absent"))
    library = [
        SCHISM,
        make_track("11", "Tool", "Schism"),
        make_track("12", "tool", "Schism (Remastered)"),
        DELIV,
        make_track("13", "Opeth", "Deliverance"),
        YYZ,
        make_track("14", "Rush", "YYZ"),
    ]
    music = FakeMusic({"Library": library, "Road": [SCHISM, YYZ]})
    assert review_counts(music, cache) == {"Library": 2, "Road": 1}


def test_matching_is_normalised(cache):
    queue(cache, ("Tool", "Schism"))
    remaster = make_track("7", "tool", "Schism (Remastered)")
    assert review_counts(FakeMusic({"Road": [remaster]}), cache) == {"Road": 1}


def test_bass_tuning_playlists_excluded(cache):
    queue(cache, ("Tool", "Schism"))
    music = FakeMusic(
        {
            "Road": [SCHISM],
            "Bass %s Drop D" % D: [SCHISM],
            "Bass 5-String %s B Standard" % D: [SCHISM],
        }
    )
    assert review_counts(music, cache) == {"Road": 1}


def test_guitar_tuning_playlist_counted_in_bass_cache(cache):
    queue(cache, ("Tool", "Schism"))
    music = FakeMusic({"Guitar %s Drop D" % D: [SCHISM], "Bass %s Drop D" % D: [SCHISM]})
    assert review_counts(music, cache) == {"Guitar %s Drop D" % D: 1}


def test_guitar_cache_excludes_guitar_tuning_playlists_only(guitar_cache):
    queue(guitar_cache, ("Tool", "Schism"))
    music = FakeMusic({"Guitar %s Drop D" % D: [SCHISM], "Bass %s Drop D" % D: [SCHISM]})
    assert review_counts(music, guitar_cache) == {"Bass %s Drop D" % D: 1}


def test_other_instrument_queue_ignored(tmp_path):
    bass = Cache(tmp_path / "t.db", "bass")
    guitar = Cache(tmp_path / "t.db", "guitar")
    try:
        queue(guitar, ("Tool", "Schism"))
        music = FakeMusic({"Road": [SCHISM]})
        assert review_counts(music, bass) == {}
        assert review_counts(music, guitar) == {"Road": 1}
    finally:
        bass.close()
        guitar.close()


def test_changes_nothing(cache):
    queue(cache, ("Tool", "Schism"))
    cache.put("Rush", "YYZ", Entry(T("D A D G"), "ug-bass", True))
    music = FakeMusic({"Road": [SCHISM, DELIV, YYZ]})
    review_counts(music, cache)
    assert music.add_calls == []
    assert music.ensure_calls == []
    assert list(music.playlists) == ["Road"]
    # Counting again gives the same answer and the queue still holds the song.
    assert review_counts(music, cache) == {"Road": 1}
    assert cache.get("Rush", "YYZ") is not None


def test_uses_one_bulk_read_not_get_tracks(cache):
    queue(cache, ("Tool", "Schism"))
    music = NoGetTracksMusic({"A": [SCHISM], "B": [SCHISM], "C": [YYZ]})
    assert review_counts(music, cache) == {"A": 1, "B": 1}
    assert music.all_calls == 1


def test_music_error_propagates(cache):
    with pytest.raises(MusicError):
        review_counts(BrokenMusic({"A": []}), cache)
