from __future__ import annotations

from typing import List, Tuple

import pytest
from conftest import FakeMusic, FakeSource, T, make_match, make_track
from typer.testing import CliRunner

from tune_sort.cache import Cache, Entry
from tune_sort.cli import make_app

DASH = "–"
ARROW = "→"
DROP_D = "Bass %s Drop D" % DASH
G_DROP_D = "Guitar %s Drop D" % DASH
B5_PLAYLIST = "Bass 5-String %s B Standard" % DASH

BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]
GUITAR_DEFAULT = ["ug-pro", "ug-tab", "songsterr"]

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Nobody", "Nothing")
C = make_track("C", "Opeth", "Deliverance")
GOLIATH = make_track("G", "Karnivool", "Goliath")

runner = CliRunner()


class Factory:
    """Sources factory; records the (instrument, names) it is asked for."""

    def __init__(self, sources=None):
        self.requested: List[Tuple[str, List[str]]] = []
        self.sources = sources if sources is not None else [
            FakeSource("s", {("Tool", "Schism"): make_match("D A D G", "ug-bass")})
        ]

    def __call__(self, instrument, names):
        self.requested.append((instrument, list(names)))
        return self.sources


def guitar_factory():
    return Factory(
        [
            FakeSource(
                "gs",
                {
                    ("Tool", "Schism"): make_match(
                        "D A D G B E", "ug-pro", instrument="guitar"
                    )
                },
            )
        ]
    )


def invoke(music, args, cache_path, factory=None, input=None):
    """Run the CLI. `sort` calls get a missing --config file so the real one is never read."""
    factory = factory or Factory()
    args = list(args)
    if args[1:2] == ["sort"] and "--config" not in args:
        args += ["--config", str(cache_path.parent / "missing.toml")]
    app = make_app(lambda: music, factory)
    return runner.invoke(app, args + ["--cache", str(cache_path)], input=input), factory


def test_playlists(cache_path):
    music = FakeMusic({"Road": [A], "Chill": []})
    result, _ = invoke(music, ["playlists"], cache_path)
    assert result.exit_code == 0
    lines = [ln.strip() for ln in result.output.splitlines()]
    assert "Road" in lines
    assert "Chill" in lines


def test_old_top_level_commands_are_gone(cache_path):
    for command in (["sort", "Road"], ["review"], ["set", "Tool", "Schism", "Drop D"]):
        result, _ = invoke(FakeMusic({"Road": [A]}), command, cache_path)
        assert result.exit_code != 0, command


def test_sort(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path)
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


def test_sort_prints_no_progress_when_not_a_terminal(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Looking up" not in result.output
    assert "[1/" not in result.output
    assert "[2/" not in result.output
    assert "Tool %s Schism %s %s (ug-bass)" % (DASH, ARROW, DROP_D) in result.output


def test_sort_dry_run_prints_no_progress_when_not_a_terminal(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["bass", "sort", "Road", "--dry-run"], cache_path)
    assert "Looking up" not in result.output
    assert "[1/" not in result.output


def test_sort_rerun_reports_already_present(cache_path):
    music = FakeMusic({"Road": [A]})
    invoke(music, ["bass", "sort", "Road"], cache_path)
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path)
    assert result.exit_code == 0
    assert "Already present: 1" in result.output
    assert "Created playlist" not in result.output
    assert "Needs review: 0" in result.output


def test_sort_dry_run(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road", "--dry-run"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Would add 1 to %s" % DROP_D in result.output
    assert "Added 1" not in result.output
    assert music.ensure_calls == []
    assert music.add_calls == []
    assert list(music.playlists) == ["Road"]


def test_sort_dry_run_says_would_create(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["bass", "sort", "Road", "--dry-run"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Would create playlist: %s" % DROP_D in result.output
    assert "Created playlist:" not in result.output


def test_sort_missing_playlist(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["bass", "sort", "Nope"], cache_path)
    assert result.exit_code == 1
    assert result.output.strip() != ""
    assert music.add_calls == []


def test_sort_source_option(cache_path):
    music = FakeMusic({"Road": [A]})
    _, f = invoke(music, ["bass", "sort", "Road"], cache_path)
    assert f.requested == [("bass", BASS_DEFAULT)]
    _, f = invoke(
        FakeMusic({"Road": [A]}), ["bass", "sort", "Road", "--source", "ug"], cache_path
    )
    assert f.requested == [("bass", ["ug-pro", "ug-bass"])]
    _, f = invoke(
        FakeMusic({"Road": [A]}), ["bass", "sort", "Road", "--source", "songsterr"], cache_path
    )
    assert f.requested == [("bass", ["songsterr"])]


# ------------------------------------------------------ sort offers to review at the end


def test_sort_asks_to_review_when_songs_need_it(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path, input="n\n")
    assert result.exit_code == 0, result.output
    assert "Review 1 songs now?" in result.output


def test_sort_review_question_counts_songs(cache_path):
    music = FakeMusic({"Road": [A, B, C]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path, input="n\n")
    assert "Review 2 songs now?" in result.output


def test_sort_never_asks_when_nothing_needs_review(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path)
    assert result.exit_code == 0
    assert "songs now?" not in result.output


def test_sort_answer_no_does_not_review(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path, input="n\n")
    assert "Type a tuning" not in result.output
    assert music.playlists[DROP_D] == [A]
    assert _entry(cache_path, "Nobody", "Nothing") is None
    assert result.output.count("Already present:") == 1


def test_sort_eof_counts_as_no(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Type a tuning" not in result.output
    assert _entry(cache_path, "Nobody", "Nothing") is None


def test_sort_answer_yes_reviews_and_resorts(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path, input="y\nDrop D\n")
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Review 1 songs now?" in out
    assert "Set Nobody %s Nothing to Drop D (%s)" % (DASH, DROP_D) in out
    assert music.playlists[DROP_D] == [A, B]
    assert out.count("Added 1 to %s" % DROP_D) == 2
    assert out.count("Already present:") == 2
    assert _entry(cache_path, "Nobody", "Nothing") == Entry(T("D A D G"), "manual", True)


def test_sort_review_flag_skips_question(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(
        music, ["bass", "sort", "Road", "--review"], cache_path, input="Drop D\n"
    )
    assert result.exit_code == 0, result.output
    assert "songs now?" not in result.output
    assert music.playlists[DROP_D] == [A, B]
    assert result.output.count("Added 1 to %s" % DROP_D) == 2


def test_sort_no_review_flag_never_prompts(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(
        music, ["bass", "sort", "Road", "--no-review"], cache_path, input="y\nDrop D\n"
    )
    assert result.exit_code == 0, result.output
    assert "songs now?" not in result.output
    assert "Type a tuning" not in result.output
    assert music.playlists[DROP_D] == [A]
    assert _entry(cache_path, "Nobody", "Nothing") is None


def test_sort_review_all_skipped_does_not_resort(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road", "--review"], cache_path, input="s\n")
    assert result.exit_code == 0, result.output
    assert result.output.count("Already present:") == 1
    assert result.output.count("Added 1 to") == 1
    assert _entry(cache_path, "Nobody", "Nothing") is None


def test_sort_review_only_offers_this_playlists_songs(cache_path):
    other = FakeMusic({"Other": [C]})
    invoke(other, ["bass", "sort", "Other", "--no-review"], cache_path)
    assert ("Opeth", "Deliverance") in _queued(cache_path)

    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(music, ["bass", "sort", "Road"], cache_path, input="y\ns\n")
    assert result.exit_code == 0, result.output
    assert "Review 1 songs now?" in result.output
    assert "Opeth" not in result.output
    assert ("Opeth", "Deliverance") in _queued(cache_path)


def test_sort_dry_run_review_leaves_music_unchanged(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(
        music, ["bass", "sort", "Road", "--dry-run", "--review"], cache_path, input="Drop D\n"
    )
    assert result.exit_code == 0, result.output
    assert music.ensure_calls == []
    assert music.add_calls == []
    assert list(music.playlists) == ["Road"]
    assert "Would add" in result.output
    assert "Added " not in result.output
    assert _entry(cache_path, "Nobody", "Nothing") == Entry(T("D A D G"), "manual", True)
    # The re-sort sees the answered song too.
    assert "Would add 2 to %s" % DROP_D in result.output


def _queue(cache_path, items, instrument="bass"):
    c = Cache(cache_path, instrument)
    for artist, title, cands in items:
        c.add_review(artist, title, cands)
    c.close()


def _entry(cache_path, artist, title, instrument="bass"):
    c = Cache(cache_path, instrument)
    try:
        return c.get(artist, title)
    finally:
        c.close()


def _queued(cache_path, instrument="bass"):
    c = Cache(cache_path, instrument)
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

GOLIATH_CANDS = [
    make_match("B E A D", "ug-bass", True, artist="Karnivool", title="Goliath"),
    make_match("B E A D G C", "songsterr", True, artist="Karnivool", title="Goliath"),
]
GOLIATH_LINE_1 = (
    "  1) B Standard (B E A D) %s Bass %s B Standard (ug-bass: Karnivool %s Goliath)"
    % (ARROW, DASH, DASH)
)
GOLIATH_LINE_2 = (
    "  2) B Standard (B E A D G C) %s Bass 6-String %s B Standard "
    "(songsterr: Karnivool %s Goliath)" % (ARROW, DASH, DASH)
)

PROMPT_WITH = "Choose 1-2, type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"
PROMPT_NONE = "Type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"


def test_review_empty(cache_path):
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path)
    assert result.exit_code == 0
    assert "Nothing to review." in result.output


def test_review_shows_candidates(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert result.exit_code == 0
    out = result.output
    assert "Tool %s Schism" % DASH in out
    assert (
        "  1) Drop D (D A D G) %s Bass %s Drop D (ug-bass: Tool %s Schism (Live))"
        % (ARROW, DASH, DASH)
        in out
    )
    assert (
        "  2) Eb Standard (Eb Ab Db Gb) %s Bass %s Eb Standard "
        "(songsterr: Tool %s Schism (Demo))" % (ARROW, DASH, DASH)
        in out
    )
    assert "No tunings found." not in out


def test_review_shows_notes_for_standard_tuning(cache_path):
    _queue(cache_path, [("Billie Eilish", "bad guy", BILLIE_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert (
        "  1) E Standard (E A D G) %s Bass %s E Standard "
        "(ug-bass: Billie Eilish %s bad guy)" % (ARROW, DASH, DASH)
        in result.output
    )


def test_review_omits_notes_when_name_is_the_notes(cache_path):
    cand = make_match("D A D Gb", "ug-bass", True, artist="Tool", title="Schism")
    _queue(cache_path, [("Tool", "Schism", [cand])])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    out = result.output
    assert (
        "  1) D A D Gb %s Bass %s D A D Gb (ug-bass: Tool %s Schism)" % (ARROW, DASH, DASH)
        in out
    )
    assert "D A D Gb (D A D Gb)" not in out


def test_review_goliath_candidates_show_string_count(cache_path):
    _queue(cache_path, [("Karnivool", "Goliath", GOLIATH_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert result.exit_code == 0, result.output
    assert GOLIATH_LINE_1 in result.output
    assert GOLIATH_LINE_2 in result.output


def test_review_goliath_pick_six_string(cache_path):
    _queue(cache_path, [("Karnivool", "Goliath", GOLIATH_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="2\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Karnivool", "Goliath")
    assert e == Entry(T("B E A D G C"), "manual", True)
    assert e.tuning.string_count == 6
    assert _queued(cache_path) == []


def test_review_goliath_pick_four_string(cache_path):
    _queue(cache_path, [("Karnivool", "Goliath", GOLIATH_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="1\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Karnivool", "Goliath")
    assert e is not None
    assert e.tuning == T("B E A D")
    assert e.tuning.string_count == 4


def test_sort_review_step_shows_string_count_in_candidates(cache_path):
    ug = FakeSource("ug", {("Karnivool", "Goliath"): GOLIATH_CANDS[0]})
    sg = FakeSource("songsterr", {("Karnivool", "Goliath"): GOLIATH_CANDS[1]})
    music = FakeMusic({"Road": [GOLIATH]})
    result, _ = invoke(
        music,
        ["bass", "sort", "Road", "--review"],
        cache_path,
        factory=Factory([ug, sg]),
        input="s\n",
    )
    assert result.exit_code == 0, result.output
    assert GOLIATH_LINE_1 in result.output
    assert GOLIATH_LINE_2 in result.output
    # The two exact matches disagree on string count, so nothing is sorted.
    assert _entry(cache_path, "Karnivool", "Goliath") is None


def test_review_prompt_with_candidates(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert "Choose 1-2" in result.output
    assert "type a tuning" in result.output
    assert PROMPT_WITH in result.output


def test_review_no_candidates_message_and_prompt(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert result.exit_code == 0
    out = result.output
    assert "No tunings found." in out
    assert PROMPT_NONE in out
    assert "Choose 1-" not in out


def test_review_pick_candidate_number(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="2\n")
    assert result.exit_code == 0
    e = _entry(cache_path, "Tool", "Schism")
    assert e is not None
    assert e.tuning == T("Eb Ab Db Gb")
    assert e.confirmed is True
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Eb Standard (Bass %s Eb Standard)" % (DASH, DASH) in result.output


def test_review_type_tuning_name(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="Drop C\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("C G C F"), "manual", True)
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Drop C (Bass %s Drop C)" % (DASH, DASH) in result.output


def test_review_typed_tuning_overrides_candidates(cache_path):
    _queue(cache_path, [("Billie Eilish", "bad guy", BILLIE_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="B E A D G\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Billie Eilish", "bad guy")
    assert e == Entry(T("B E A D G"), "manual", True)
    assert e.tuning.string_count == 5
    assert _queued(cache_path) == []
    expected = "Set Billie Eilish %s bad guy to B Standard (%s)" % (DASH, B5_PLAYLIST)
    assert expected in result.output


def test_review_no_candidates_type_tuning(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="Drop D\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("D A D G"), "manual", True)
    assert _queued(cache_path) == []
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, DROP_D) in result.output


@pytest.mark.parametrize("answer", ["BEADG", "5-string B Standard"])
def test_review_typed_five_string_forms(cache_path, answer):
    _queue(cache_path, [("Billie Eilish", "bad guy", BILLIE_CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input=answer + "\n")
    assert result.exit_code == 0, result.output
    assert _entry(cache_path, "Billie Eilish", "bad guy") == Entry(
        T("B E A D G"), "manual", True
    )
    assert _queued(cache_path) == []


def test_review_typed_guitar_tuning_reduced_to_bass(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="EADGBE\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Tool", "Schism")
    assert e == Entry(T("E A D G"), "manual", True)
    assert "Set Tool %s Schism to E Standard (Bass %s E Standard)" % (DASH, DASH) in result.output


def test_review_invalid_then_valid(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="banana\nDrop C\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("C G C F"), "manual", True)
    assert result.output.count("Tool %s Schism" % DASH) >= 1
    assert _queued(cache_path) == []


def test_review_skip(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\nDrop D\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") is None
    assert _entry(cache_path, "Opeth", "Deliverance") is not None
    assert _queued(cache_path) == [("Tool", "Schism")]


def test_review_quit(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="q\n")
    assert result.exit_code == 0
    assert _entry(cache_path, "Tool", "Schism") is None
    assert _entry(cache_path, "Opeth", "Deliverance") is None
    assert len(_queued(cache_path)) == 2


def test_set(cache_path):
    result, _ = invoke(FakeMusic(), ["bass", "set", "Tool", "Schism", "Drop D"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, DROP_D) in result.output
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("D A D G"), "manual", True)


def test_set_guitar_tuning_reduced(cache_path):
    result, _ = invoke(FakeMusic(), ["bass", "set", "Tool", "Schism", "EADGBE"], cache_path)
    assert result.exit_code == 0, result.output
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("E A D G"), "manual", True)
    assert "E Standard (Bass %s E Standard)" % DASH in result.output


def test_set_five_string_prints_playlist(cache_path):
    result, _ = invoke(
        FakeMusic(),
        ["bass", "set", "Billie Eilish", "bad guy", "5-string B Standard"],
        cache_path,
    )
    assert result.exit_code == 0, result.output
    expected = "Set Billie Eilish %s bad guy to B Standard (%s)" % (DASH, B5_PLAYLIST)
    assert expected in result.output


def test_set_removes_from_review_queue(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    invoke(FakeMusic(), ["bass", "set", "Tool", "Schism", "Drop D"], cache_path)
    assert _queued(cache_path) == []


def test_set_invalid_tuning(cache_path):
    result, _ = invoke(FakeMusic(), ["bass", "set", "Tool", "Schism", "banana"], cache_path)
    assert result.exit_code == 1
    assert _entry(cache_path, "Tool", "Schism") is None


# ===================================================================== guitar commands

G_CANDS = [
    make_match("D A D G B E", "ug-pro", True, instrument="guitar"),
    make_match("E A D G B E", "songsterr", True, instrument="guitar"),
]
G_PROMPT_WITH = "Choose 1-2, type a tuning (e.g. Drop D or D A D G B E), s to skip, q to quit"
G_PROMPT_NONE = "Type a tuning (e.g. Drop D or D A D G B E), s to skip, q to quit"


def test_guitar_sort(cache_path):
    music = FakeMusic({"Road": [A, B]})
    f = guitar_factory()
    result, _ = invoke(music, ["guitar", "sort", "Road"], cache_path, factory=f)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Tool %s Schism %s %s (ug-pro)" % (DASH, ARROW, G_DROP_D) in out
    assert "Nobody %s Nothing %s needs review" % (DASH, ARROW) in out
    assert "Created playlist: %s" % G_DROP_D in out
    assert music.playlists[G_DROP_D] == [A]
    assert not any(name.startswith("Bass") for name in music.playlists)
    assert f.requested == [("guitar", GUITAR_DEFAULT)]


def test_guitar_sort_source_option(cache_path):
    f = guitar_factory()
    invoke(
        FakeMusic({"Road": [A]}),
        ["guitar", "sort", "Road", "--source", "songsterr"],
        cache_path,
        factory=f,
    )
    assert f.requested == [("guitar", ["songsterr"])]


def test_guitar_sort_dry_run(cache_path):
    music = FakeMusic({"Road": [A]})
    result, _ = invoke(
        music, ["guitar", "sort", "Road", "--dry-run"], cache_path, factory=guitar_factory()
    )
    assert result.exit_code == 0, result.output
    assert "Would create playlist: %s" % G_DROP_D in result.output
    assert "Would add 1 to %s" % G_DROP_D in result.output
    assert music.add_calls == []
    assert music.ensure_calls == []


def test_guitar_sort_missing_playlist(cache_path):
    result, _ = invoke(
        FakeMusic({"Road": [A]}), ["guitar", "sort", "Nope"], cache_path, factory=guitar_factory()
    )
    assert result.exit_code == 1


def test_guitar_sort_review_step_resorts_into_guitar_playlist(cache_path):
    music = FakeMusic({"Road": [A, B]})
    result, _ = invoke(
        music,
        ["guitar", "sort", "Road", "--review"],
        cache_path,
        factory=guitar_factory(),
        input="Drop D\n",
    )
    assert result.exit_code == 0, result.output
    assert music.playlists[G_DROP_D] == [A, B]
    assert "Set Nobody %s Nothing to Drop D (%s)" % (DASH, G_DROP_D) in result.output
    assert _entry(cache_path, "Nobody", "Nothing", "guitar") == Entry(
        T("D A D G B E", "guitar"), "manual", True
    )
    assert _entry(cache_path, "Nobody", "Nothing", "bass") is None


def test_bass_and_guitar_sort_do_not_share_cache_or_playlists(cache_path):
    music = FakeMusic({"Road": [A]})
    invoke(music, ["bass", "sort", "Road"], cache_path)
    result, _ = invoke(music, ["guitar", "sort", "Road"], cache_path, factory=guitar_factory())
    assert result.exit_code == 0, result.output
    assert music.playlists[DROP_D] == [A]
    assert music.playlists[G_DROP_D] == [A]
    assert "Created playlist: %s" % G_DROP_D in result.output
    assert "Already present: 0" in result.output


def test_guitar_review_does_not_show_bass_queue(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)], "bass")
    result, _ = invoke(FakeMusic(), ["guitar", "review"], cache_path)
    assert result.exit_code == 0
    assert "Nothing to review." in result.output
    assert "Schism" not in result.output


def test_bass_review_does_not_show_guitar_queue(cache_path):
    _queue(cache_path, [("Tool", "Schism", G_CANDS)], "guitar")
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path)
    assert "Nothing to review." in result.output
    assert "Schism" not in result.output


def test_guitar_review_candidate_lines(cache_path):
    _queue(cache_path, [("Tool", "Schism", G_CANDS)], "guitar")
    result, _ = invoke(FakeMusic(), ["guitar", "review"], cache_path, input="s\n")
    assert result.exit_code == 0, result.output
    out = result.output
    assert (
        "  1) Drop D (D A D G B E) %s Guitar %s Drop D (ug-pro: Tool %s Schism)"
        % (ARROW, DASH, DASH)
        in out
    )
    assert (
        "  2) E Standard (E A D G B E) %s Guitar %s E Standard (songsterr: Tool %s Schism)"
        % (ARROW, DASH, DASH)
        in out
    )


def test_guitar_review_prompts(cache_path):
    _queue(cache_path, [("Tool", "Schism", G_CANDS), ("Opeth", "Deliverance", [])], "guitar")
    result, _ = invoke(FakeMusic(), ["guitar", "review"], cache_path, input="s\ns\n")
    assert G_PROMPT_WITH in result.output
    assert G_PROMPT_NONE in result.output
    assert "e.g. Drop D or B E A D G)" not in result.output


def test_bass_review_prompt_keeps_bass_example(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])], "bass")
    result, _ = invoke(FakeMusic(), ["bass", "review"], cache_path, input="s\n")
    assert PROMPT_NONE in result.output
    assert "D A D G B E" not in result.output


def test_guitar_review_pick_candidate_stores_guitar_entry(cache_path):
    _queue(cache_path, [("Tool", "Schism", G_CANDS)], "guitar")
    result, _ = invoke(FakeMusic(), ["guitar", "review"], cache_path, input="2\n")
    assert result.exit_code == 0, result.output
    e = _entry(cache_path, "Tool", "Schism", "guitar")
    assert e is not None
    assert e.tuning == T("E A D G B E", "guitar")
    assert e.confirmed is True
    assert _entry(cache_path, "Tool", "Schism", "bass") is None
    assert _queued(cache_path, "guitar") == []
    assert "Set Tool %s Schism to E Standard (Guitar %s E Standard)" % (DASH, DASH) in result.output


def test_guitar_review_typed_tuning(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])], "guitar")
    result, _ = invoke(FakeMusic(), ["guitar", "review"], cache_path, input="DADGBE\n")
    assert result.exit_code == 0, result.output
    assert _entry(cache_path, "Tool", "Schism", "guitar") == Entry(
        T("D A D G B E", "guitar"), "manual", True
    )
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, G_DROP_D) in result.output


def test_guitar_review_invalid_answer_asks_again(cache_path):
    _queue(cache_path, [("Tool", "Schism", [])], "guitar")
    result, _ = invoke(
        FakeMusic(), ["guitar", "review"], cache_path, input="E A D G\nOpen G\n"
    )
    assert result.exit_code == 0, result.output
    assert _entry(cache_path, "Tool", "Schism", "guitar").tuning == T("D G D G B D", "guitar")


def test_guitar_set(cache_path):
    result, _ = invoke(FakeMusic(), ["guitar", "set", "Tool", "Schism", "Drop D"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Set Tool %s Schism to Drop D (%s)" % (DASH, G_DROP_D) in result.output
    assert _entry(cache_path, "Tool", "Schism", "guitar") == Entry(
        T("D A D G B E", "guitar"), "manual", True
    )
    assert _entry(cache_path, "Tool", "Schism", "bass") is None


def test_guitar_set_open_and_seven_string(cache_path):
    result, _ = invoke(FakeMusic(), ["guitar", "set", "A", "T", "Open G"], cache_path)
    assert "Set A %s T to Open G (Guitar %s Open G)" % (DASH, DASH) in result.output
    result, _ = invoke(
        FakeMusic(), ["guitar", "set", "A", "U", "7-string B Standard"], cache_path
    )
    assert "(Guitar 7-String %s B Standard)" % DASH in result.output
    assert _entry(cache_path, "A", "U", "guitar").tuning.string_count == 7


def test_guitar_set_six_string_not_reduced(cache_path):
    result, _ = invoke(FakeMusic(), ["guitar", "set", "A", "T", "EADGBE"], cache_path)
    assert result.exit_code == 0, result.output
    assert "E Standard (Guitar %s E Standard)" % DASH in result.output
    assert _entry(cache_path, "A", "T", "guitar").tuning.string_count == 6


def test_guitar_set_invalid_tuning(cache_path):
    for bad in ("banana", "E A D G"):
        result, _ = invoke(FakeMusic(), ["guitar", "set", "A", "T", bad], cache_path)
        assert result.exit_code == 1, bad
    assert _entry(cache_path, "A", "T", "guitar") is None


def test_guitar_set_removes_only_guitar_review_item(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)], "bass")
    _queue(cache_path, [("Tool", "Schism", G_CANDS)], "guitar")
    invoke(FakeMusic(), ["guitar", "set", "Tool", "Schism", "Drop D"], cache_path)
    assert _queued(cache_path, "guitar") == []
    assert _queued(cache_path, "bass") == [("Tool", "Schism")]
