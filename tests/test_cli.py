from __future__ import annotations

from typing import List

import pytest
from conftest import FakeMusic, FakeSource, T, make_match, make_track
from typer.testing import CliRunner

from bass_sort.cache import Cache, Entry
from bass_sort.cli import make_app

DASH = "–"
ARROW = "→"
DROP_D = "Bass %s Drop D" % DASH
B5_PLAYLIST = "Bass 5-String %s B Standard" % DASH

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Nobody", "Nothing")

runner = CliRunner()


class Factory:
    def __init__(self, sources=None):
        self.requested: List[str] = []
        self.sources = sources if sources is not None else [
            FakeSource("s", {("Tool", "Schism"): make_match("D A D G", "ug-bass")})
        ]

    def __call__(self, which):
        self.requested.append(which)
        return self.sources


def invoke(music, args, cache_path, factory=None, input=None):
    factory = factory or Factory()
    app = make_app(lambda: music, factory)
    return runner.invoke(app, list(args) + ["--cache", str(cache_path)], input=input), factory


def test_playlists(cache_path):
    music = FakeMusic({"Road": [A], "Chill": []})
    result, _ = invoke(music, ["playlists"], cache_path)
    assert result.exit_code == 0
    lines = [ln.strip() for ln in result.output.splitlines()]
    assert "Road" in lines
    assert "Chill" in lines


def test_sort(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["sort", "Road"], cache_path)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Tool %s Schism %s %s (ug-bass)" % (DASH, ARROW, DROP_D) in out
    assert "Nobody %s Nothing %s needs review" % (DASH, ARROW) in out
    assert "Created playlist: %s" % DROP_D in out
    assert "Would create playlist" not in out
    assert "Added 1 to %s" % DROP_D in out
    assert "Already present: 0" in out
    assert "Needs review: 1" in out
    assert music.playlists[DROP_D] == [A]


def test_sort_rerun_reports_already_present(cache_path):
    music = FakeMusic({"Road": [A]})
    invoke(music, ["sort", "Road"], cache_path)
    result, _ = invoke(music, ["sort", "Road"], cache_path)
    assert result.exit_code == 0
    assert "Already present: 1" in result.output
    assert "Created playlist" not in result.output
    assert "Needs review: 0" in result.output


def test_sort_dry_run(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["sort", "Road", "--dry-run"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Would add 1 to %s" % DROP_D in result.output
    assert "Added 1" not in result.output
    assert music.ensure_calls == []
    assert music.add_calls == []
    assert list(music.playlists) == ["Road"]


def test_sort_dry_run_says_would_create(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["sort", "Road", "--dry-run"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Would create playlist: %s" % DROP_D in result.output
    assert "Created playlist:" not in result.output


def test_sort_missing_playlist(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["sort", "Nope"], cache_path)
    assert result.exit_code == 1
    assert result.output.strip() != ""
    assert music.add_calls == []


def test_sort_source_option(cache_path):
    music = FakeMusic({"Road": [A]})
    _, f = invoke(music, ["sort", "Road"], cache_path)
    assert f.requested == ["both"]
    _, f = invoke(FakeMusic({"Road": [A]}), ["sort", "Road", "--source", "ug"], cache_path)
    assert f.requested == ["ug"]
    _, f = invoke(
        FakeMusic({"Road": [A]}), ["sort", "Road", "--source", "songsterr"], cache_path
    )
    assert f.requested == ["songsterr"]


def _queue(cache_path, items):
    c = Cache(cache_path)
    for artist, title, cands in items:
        c.add_review(artist, title, cands)
    c.close()


def _entry(cache_path, artist, title):
    c = Cache(cache_path)
    try:
        return c.get(artist, title)
    finally:
        c.close()


def _queued(cache_path):
    c = Cache(cache_path)
    try:
        return [(i.artist, i.title) for i in c.review_items()]
    finally:
        c.close()


CANDS = [
    make_match("D A D G", "ug-bass", False, title="Schism (Live)"),
    make_match("D# G# C# F#", "songsterr", False, artist="Tool", title="Schism (Demo)"),
]

BILLIE_CANDS = [
    make_match("E A D G", "ug-bass", True, artist="Billie Eilish", title="bad guy"),
    make_match("D G C F", "songsterr", True, artist="Billie Eilish", title="bad guy"),
]

PROMPT_WITH = "Choose 1-2, type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"
PROMPT_NONE = "Type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"


def test_review_empty(cache_path):
    result, _ = invoke(FakeMusic(), ["review"], cache_path)
    assert result.exit_code == 0
    assert "Nothing to review." in result.output


def test_review_shows_candidates(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="s\n")
    assert result.exit_code == 0
    out = result.output
    assert "Tool %s Schism" % DASH in out
    assert "1) Drop D (ug-bass: Tool %s Schism (Live))" % DASH in out
    assert "2) Eb Standard (songsterr: Tool %s Schism (Demo))" % DASH in out
    assert "No tunings found." not in out


def test_review_prompt_with_candidates(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="s\n")
    assert "Choose 1-2" in result.output
    assert "type a tuning" in result.output
    assert PROMPT_WITH in result.output


def test_review_no_candidates_message_and_prompt(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="s\n")
    assert result.exit_code == 0
    out = result.output
    assert "No tunings found." in out
    assert PROMPT_NONE in out
    assert "Choose 1-" not in out


def test_review_pick_candidate_number(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="2\n")
    assert result.exit_code == 0
    e = _entry(cache_path, "Tool", "Schism")
    assert e is not None
    assert e.tuning == T("Eb Ab Db Gb")
    assert e.confirmed is True
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Eb Standard (Bass %s Eb Standard)" % (DASH, DASH) in result.output


def test_review_type_tuning_name(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="Drop C\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("C G C F"), "manual", True)
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Drop C (Bass %s Drop C)" % (DASH, DASH) in result.output


def test_review_typed_tuning_overrides_candidates(cache_path):
    _queue(cache_path, [("Billie Eilish", "bad guy", BILLIE_CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="B E A D G\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Billie Eilish", "bad guy")
    assert e == Entry(T("B E A D G"), "manual", True)
    assert e.tuning.string_count == 5
    assert _queued(cache_path) == []
    expected = "Set Billie Eilish %s bad guy to B Standard (%s)" % (DASH, B5_PLAYLIST)
    assert expected in result.output


def test_review_no_candidates_type_tuning(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="Drop D\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("D A D G"), "manual", True)
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, DROP_D) in result.output


@pytest.mark.parametrize("answer", ["BEADG", "5-string B Standard"])
def test_review_typed_five_string_forms(cache_path, answer):
    _queue(cache_path, [("Billie Eilish", "bad guy", BILLIE_CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input=answer + "\n")
    assert result.exit_code == 0, result.output
    assert _entry(cache_path, "Billie Eilish", "bad guy") == Entry(
        T("B E A D G"), "manual", True
    )
    assert _queued(cache_path) == []


def test_review_invalid_then_valid(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="banana\nDrop C\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("C G C F"), "manual", True)
    assert result.output.count("Tool %s Schism" % DASH) >= 1
    assert _queued(cache_path) == []


def test_review_skip(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="s\nDrop D\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") is None
    assert _entry(cache_path, "Opeth", "Deliverance") is not None
    assert _queued(cache_path) == [("Tool", "Schism")]


def test_review_quit(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result, _ = invoke(FakeMusic(), ["review"], cache_path, input="q\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") is None
    assert _entry(cache_path, "Opeth", "Deliverance") is None
    assert len(_queued(cache_path)) == 2


def test_set(cache_path):
    result, _ = invoke(FakeMusic(), ["set", "Tool", "Schism", "Drop D"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, DROP_D) in result.output
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("D A D G"), "manual", True)


def test_set_five_string_prints_playlist(cache_path):
    result, _ = invoke(
        FakeMusic(), ["set", "Billie Eilish", "bad guy", "5-string B Standard"], cache_path
    )
    assert result.exit_code == 0, result.output
    expected = "Set Billie Eilish %s bad guy to B Standard (%s)" % (DASH, B5_PLAYLIST)
    assert expected in result.output


def test_set_removes_from_review_queue(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    invoke(FakeMusic(), ["set", "Tool", "Schism", "Drop D"], cache_path)
    assert _queued(cache_path) == []


def test_set_invalid_tuning(cache_path):
    result, _ = invoke(FakeMusic(), ["set", "Tool", "Schism", "banana"], cache_path)
    assert result.exit_code == 1
    assert _entry(cache_path, "Tool", "Schism") is None
