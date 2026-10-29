from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import FakeFetch, T, fixture_text

from tune_sort.sources import FetchError, SourceError
from tune_sort.sources.songsterr import SEARCH_URL, Songsterr, search_url


def track(instrument_id, tuning, name="t"):
    return {"instrumentId": instrument_id, "instrument": "x", "name": name, "tuning": tuning}


def song(song_id, tracks, artist="Tool", title="Schism", junk=False, popular=None):
    s = {"songId": song_id, "artist": artist, "title": title, "isJunk": junk, "tracks": tracks}
    if popular is not None:
        s["popularTrackBass"] = popular
    return s


GUITAR = track(30, [64, 59, 55, 50, 45, 38])
BASS_DROP_D = track(34, [43, 38, 33, 26])
BASS_STD = track(33, [43, 38, 33, 28])


def lookup(songs_or_text):
    text = songs_or_text if isinstance(songs_or_text, str) else json.dumps(songs_or_text)
    fetch = FakeFetch({}, SEARCH_URL, text)
    return Songsterr(fetch).lookup("Tool", "Schism"), fetch


def test_search_url():
    url = search_url("Tool", "Schism")
    assert url.startswith(SEARCH_URL)
    assert parse_qs(urlparse(url).query)["pattern"] == ["Tool Schism"]


def test_real_fixture():
    m, _ = lookup(fixture_text("songsterr/search_tool_schism.json"))
    assert m is not None
    assert m.source == "songsterr"
    assert m.tuning == T("D A D G")
    assert m.tuning.name == "Drop D"
    assert m.exact is True
    assert m.url.startswith("https://www.songsterr.com/a/wa/song?id=")
    assert m.matched_artist == "Tool"
    assert m.matched_title == "Schism"


def test_url_uses_song_id():
    m, _ = lookup([song(4242, [GUITAR, BASS_STD])])
    assert m.url == "https://www.songsterr.com/a/wa/song?id=4242"
    assert m.tuning == T("E A D G")


def test_tuning_reversed_to_lowest_first():
    m, _ = lookup([song(1, [GUITAR, BASS_DROP_D])])
    assert m.tuning.pitch_classes == (2, 9, 2, 7)


def test_five_string_bass():
    m, _ = lookup([song(1, [track(33, [43, 38, 33, 28, 23])])])
    assert m.tuning.string_count == 5
    assert m.tuning.name == "B Standard"


def test_bass_track_with_guitar_tuning_reduced_to_four_strings():
    m, _ = lookup([song(1, [track(33, [64, 59, 55, 50, 45, 40])])])
    assert m is not None
    assert m.tuning.string_count == 4
    assert m.tuning.name == "E Standard"


def test_popular_track_bass_preferred():
    m, _ = lookup([song(1, [BASS_STD, GUITAR, BASS_DROP_D], popular=2)])
    assert m.tuning == T("D A D G")


def test_popular_track_not_bass_falls_back_to_first_bass():
    m, _ = lookup([song(1, [GUITAR, BASS_STD, BASS_DROP_D], popular=0)])
    assert m.tuning == T("E A D G")


def test_instrument_id_range_32_to_39():
    for iid in (32, 39):
        m, _ = lookup([song(1, [track(iid, [43, 38, 33, 28])])])
        assert m is not None
    for iid in (31, 40):
        m, _ = lookup([song(1, [track(iid, [43, 38, 33, 28])])])
        assert m is None


def test_junk_skipped():
    m, _ = lookup([song(1, [BASS_STD], junk=True), song(2, [BASS_DROP_D])])
    assert m.url.endswith("id=2")


def test_only_junk_returns_none():
    m, _ = lookup([song(1, [BASS_STD], junk=True)])
    assert m is None


def test_no_bass_track_skipped():
    m, _ = lookup([song(1, [GUITAR]), song(2, [BASS_STD])])
    assert m.url.endswith("id=2")


def test_invalid_tuning_skipped():
    m, _ = lookup([song(1, [track(34, [43, 38, 33])]), song(2, [BASS_STD])])
    assert m.url.endswith("id=2")


def test_no_usable_song_returns_none():
    m, _ = lookup([song(1, [GUITAR])])
    assert m is None


def test_empty_list_returns_none():
    m, _ = lookup([])
    assert m is None


def test_exact_preferred_over_earlier_similar():
    m, _ = lookup(
        [
            song(1, [BASS_STD], title="Schism (Live)"),
            song(2, [BASS_DROP_D]),
        ]
    )
    assert m.exact is True
    assert m.url.endswith("id=2")


def test_similar_fallback():
    m, _ = lookup([song(1, [BASS_STD], title="Schism (Live)")])
    assert m.exact is False
    assert m.matched_title == "Schism (Live)"


def test_other_artist_ignored():
    m, _ = lookup([song(1, [BASS_STD], artist="Opeth")])
    assert m is None


def test_invalid_json_returns_none():
    m, _ = lookup("<html>not json</html>")
    assert m is None


def test_fetch_error_raises_source_error():
    fetch = FakeFetch({}, SEARCH_URL, FetchError("down"))
    with pytest.raises(SourceError):
        Songsterr(fetch).lookup("Tool", "Schism")
