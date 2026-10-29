"""Songsterr lookups in guitar mode (and instrument attribute checks)."""
from __future__ import annotations

import json

import pytest

from tests.conftest import FakeFetch, T, fixture_text
from tune_sort.sources import FetchError, SourceError
from tune_sort.sources.songsterr import SEARCH_URL, Songsterr


def track(instrument_id, tuning, name="t"):
    return {"instrumentId": instrument_id, "instrument": "x", "name": name, "tuning": tuning}


def song(song_id, tracks, artist="Tool", title="Schism", junk=False, popular_guitar=None,
         popular_bass=None):
    s = {"songId": song_id, "artist": artist, "title": title, "isJunk": junk, "tracks": tracks}
    if popular_guitar is not None:
        s["popularTrackGuitar"] = popular_guitar
    if popular_bass is not None:
        s["popularTrackBass"] = popular_bass
    return s


GUITAR_STD = track(25, [64, 59, 55, 50, 45, 40])
GUITAR_DROP_D = track(30, [64, 59, 55, 50, 45, 38])
BASS_STD = track(33, [43, 38, 33, 28])


def glookup(songs_or_text, instrument="guitar"):
    text = songs_or_text if isinstance(songs_or_text, str) else json.dumps(songs_or_text)
    fetch = FakeFetch({}, SEARCH_URL, text)
    return Songsterr(fetch, instrument).lookup("Tool", "Schism")


def test_instrument_attribute():
    assert Songsterr(FakeFetch()).instrument == "bass"
    assert Songsterr(FakeFetch(), "guitar").instrument == "guitar"


def test_real_fixture_guitar_drop_d():
    m = glookup(fixture_text("songsterr/search_tool_schism.json"))
    assert m is not None
    assert m.source == "songsterr"
    assert m.tuning == T("D A D G B E", "guitar")
    assert m.tuning.name == "Drop D"
    assert m.tuning.instrument == "guitar"
    assert m.exact is True
    assert m.url.startswith("https://www.songsterr.com/a/wa/song?id=")
    assert m.matched_artist == "Tool"
    assert m.matched_title == "Schism"


def test_real_fixture_bass_still_bass():
    m = glookup(fixture_text("songsterr/search_tool_schism.json"), "bass")
    assert m.tuning == T("D A D G")
    assert m.tuning.instrument == "bass"


def test_guitar_tuning_reversed_to_lowest_first():
    m = glookup([song(7, [BASS_STD, GUITAR_STD])])
    assert m.tuning.pitch_classes == (4, 9, 2, 7, 11, 4)
    assert m.url == "https://www.songsterr.com/a/wa/song?id=7"


def test_popular_track_guitar_preferred():
    m = glookup([song(1, [GUITAR_STD, BASS_STD, GUITAR_DROP_D], popular_guitar=2)])
    assert m.tuning == T("D A D G B E", "guitar")


def test_popular_track_not_guitar_falls_back_to_first_guitar():
    m = glookup([song(1, [BASS_STD, GUITAR_STD, GUITAR_DROP_D], popular_guitar=0)])
    assert m.tuning == T("E A D G B E", "guitar")


def test_popular_track_bass_ignored_in_guitar_mode():
    m = glookup([song(1, [BASS_STD, GUITAR_STD], popular_bass=0)])
    assert m.tuning == T("E A D G B E", "guitar")


def test_instrument_id_range_24_to_31():
    for iid in (24, 31):
        assert glookup([song(1, [track(iid, [64, 59, 55, 50, 45, 40])])]) is not None
    for iid in (23, 32):
        assert glookup([song(1, [track(iid, [64, 59, 55, 50, 45, 40])])]) is None


def test_bass_only_song_gives_none_for_guitar():
    assert glookup([song(1, [BASS_STD])]) is None


def test_guitar_only_song_gives_none_for_bass():
    assert glookup([song(1, [GUITAR_STD])], "bass") is None


def test_seven_string_guitar_track():
    m = glookup([song(1, [track(27, [64, 59, 55, 50, 45, 40, 35])])])
    assert m.tuning.string_count == 7
    assert m.tuning.name == "B Standard"


def test_invalid_guitar_tuning_skipped():
    m = glookup([song(1, [track(30, [64, 59, 55, 50, 45])]), song(2, [GUITAR_STD])])
    assert m.url.endswith("id=2")


def test_junk_skipped():
    m = glookup([song(1, [GUITAR_STD], junk=True), song(2, [GUITAR_DROP_D])])
    assert m.url.endswith("id=2")


def test_exact_preferred_and_similar_fallback():
    m = glookup([song(1, [GUITAR_STD], title="Schism (Live)"), song(2, [GUITAR_DROP_D])])
    assert m.exact is True
    assert m.url.endswith("id=2")
    m2 = glookup([song(1, [GUITAR_STD], title="Schism (Live)")])
    assert m2.exact is False
    assert m2.matched_title == "Schism (Live)"


def test_parse_failure_returns_none():
    assert glookup("<html>nope</html>") is None


def test_fetch_error_raises_source_error():
    fetch = FakeFetch({}, SEARCH_URL, FetchError("down"))
    with pytest.raises(SourceError):
        Songsterr(fetch, "guitar").lookup("Tool", "Schism")
