"""CLI: --recheck, lookup failures, add errors, EOF at the review prompt."""
from __future__ import annotations

from typer.testing import CliRunner

from tests.conftest import FakeMusic, FakeSource, T, failing_source, make_match, make_track
from tune_sort.cache import Cache, Entry
from tune_sort.cli import make_app
from tune_sort.sources import SourceError

DASH = "–"
ARROW = "→"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Nobody", "Nothing")
C = make_track("C", "Opeth", "Deliverance")

runner = CliRunner()

CANDS = [
    make_match("D A D G", "ug-bass", False, title="Schism (Live)"),
    make_match("D# G# C# F#", "songsterr", False, title="Schism (Demo)"),
]


class Factory:
    def __init__(self, sources):
        self.sources = sources

    def __call__(self, instrument, names):
        return self.sources


def default_sources():
    return [
        FakeSource(
            "s",
            {
                ("Tool", "Schism"): make_match("D A D G", "ug-bass"),
                ("Opeth", "Deliverance"): make_match("D# G# C# F#", "ug-bass"),
                ("Nobody", "Nothing"): make_match("D A D G", "ug-bass"),
            },
        )
    ]


def invoke(music, args, cache_path, sources=None, input=None):
    args = list(args)
    if args[1:2] == ["sort"] and "--config" not in args:
        args += ["--config", str(cache_path.parent / "missing.toml")]
    factory = Factory(sources if sources is not None else default_sources())
    app = make_app(lambda: music, factory)
    return runner.invoke(app, args + ["--cache", str(cache_path)], input=input)


def _queue(cache_path, items):
    c = Cache(cache_path, "bass")
    for artist, title, cands in items:
        c.add_review(artist, title, cands)
    c.close()


def _entry(cache_path, artist, title):
    c = Cache(cache_path, "bass")
    try:
        return c.get(artist, title)
    finally:
        c.close()


def _queued(cache_path):
    c = Cache(cache_path, "bass")
    try:
        return [(i.artist, i.title) for i in c.review_items()]
    finally:
        c.close()


# --------------------------------------------------------------------- --recheck


def test_queued_song_is_not_looked_up_without_recheck(cache_path):
    _queue(cache_path, [("Nobody", "Nothing", [])])
    sources = default_sources()
    music = FakeMusic({"Road": [A, B]})
    result = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path, sources)
    assert result.exit_code == 0, result.output
    assert sources[0].calls == [("Tool", "Schism")]
    assert "Nobody %s Nothing %s needs review" % (DASH, ARROW) in result.output
    assert "Needs review: 1" in result.output
    assert music.playlists[DROP_D] == [A]
    assert _queued(cache_path) == [("Nobody", "Nothing")]


def test_recheck_looks_queued_song_up_again(cache_path):
    _queue(cache_path, [("Nobody", "Nothing", [])])
    sources = default_sources()
    music = FakeMusic({"Road": [A, B]})
    result = invoke(
        music, ["bass", "sort", "Road", "--no-review", "--recheck"], cache_path, sources
    )
    assert result.exit_code == 0, result.output
    assert ("Nobody", "Nothing") in sources[0].calls
    assert "Needs review: 0" in result.output
    assert music.playlists[DROP_D] == [A, B]
    assert _entry(cache_path, "Nobody", "Nothing") == Entry(T("D A D G"), "ug-bass", False)
    assert _queued(cache_path) == []


def test_recheck_still_unresolved_stays_queued(cache_path):
    _queue(cache_path, [("Nobody", "Nothing", [])])
    sources = [FakeSource("s")]
    music = FakeMusic({"Road": [B]})
    result = invoke(
        music, ["bass", "sort", "Road", "--no-review", "--recheck"], cache_path, sources
    )
    assert result.exit_code == 0, result.output
    assert sources[0].calls == [("Nobody", "Nothing")]
    assert "Nobody %s Nothing %s needs review" % (DASH, ARROW) in result.output
    assert "Needs review: 1" in result.output
    assert _queued(cache_path) == [("Nobody", "Nothing")]


def test_second_sort_does_not_look_up_a_song_that_needed_review(cache_path):
    sources = [FakeSource("s")]
    music = FakeMusic({"Road": [B]})
    invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path, sources)
    assert sources[0].calls == [("Nobody", "Nothing")]
    result = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path, sources)
    assert sources[0].calls == [("Nobody", "Nothing")]
    assert "Nobody %s Nothing %s needs review" % (DASH, ARROW) in result.output
    assert "Needs review: 1" in result.output


# ---------------------------------------------------------------- lookup failures


def test_lookup_failure_line_and_summary(cache_path):
    sources = [FakeSource("s", {("Nobody", "Nothing"): SourceError("down")})]
    sources[0].answers[("Tool", "Schism")] = make_match("D A D G", "ug-bass")
    music = FakeMusic({"Road": [A, B]})
    result = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path, sources)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Nobody %s Nothing %s lookup failed (s), will retry" % (DASH, ARROW) in out
    assert "needs review" not in out
    assert "Needs review: 0" in out
    assert "Lookup failed: 1" in out
    assert out.index("Needs review: 0") < out.index("Lookup failed: 1")
    assert music.playlists[DROP_D] == [A]
    assert _queued(cache_path) == []
    assert _entry(cache_path, "Nobody", "Nothing") is None


def test_lookup_failure_line_lists_every_failed_source(cache_path):
    sources = [failing_source("ug-pro"), failing_source("songsterr")]
    result = invoke(
        FakeMusic({"Road": [A]}), ["bass", "sort", "Road", "--no-review"], cache_path, sources
    )
    assert result.exit_code == 0, result.output
    assert "Tool %s Schism %s lookup failed (ug-pro, songsterr), will retry" % (DASH, ARROW) in (
        result.output
    )


def test_no_lookup_failed_line_when_nothing_failed(cache_path):
    result = invoke(FakeMusic({"Road": [A]}), ["bass", "sort", "Road"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Lookup failed" not in result.output
    assert "lookup failed" not in result.output


def test_lookup_failed_songs_do_not_trigger_review_offer(cache_path):
    sources = [failing_source("s")]
    result = invoke(FakeMusic({"Road": [A]}), ["bass", "sort", "Road"], cache_path, sources)
    assert result.exit_code == 0, result.output
    assert "songs now?" not in result.output
    assert "Lookup failed: 1" in result.output


def test_lookup_failed_song_is_looked_up_on_next_sort(cache_path):
    music = FakeMusic({"Road": [A]})
    invoke(music, ["bass", "sort", "Road"], cache_path, [failing_source("s")])
    result = invoke(music, ["bass", "sort", "Road"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Lookup failed" not in result.output
    assert music.playlists[DROP_D] == [A]


# ------------------------------------------------------------------- add errors


def test_add_error_is_reported_and_sort_continues(cache_path):
    music = FakeMusic({"Road": [A, C, B]}, fail_add={"C": "boom"})
    result = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path)
    assert result.exit_code == 0, result.output
    out = result.output
    assert "Couldn't add Opeth %s Deliverance to %s: boom" % (DASH, EB_STD) in out
    assert out.index("Needs review:") < out.index("Couldn't add")
    assert music.playlists[DROP_D] == [A, B]
    assert "Added 2 to %s" % DROP_D in out
    # Every track is still printed.
    assert "Tool %s Schism %s %s" % (DASH, ARROW, DROP_D) in out
    assert "Opeth %s Deliverance %s %s" % (DASH, ARROW, EB_STD) in out
    assert "Nobody %s Nothing %s %s" % (DASH, ARROW, DROP_D) in out


def test_each_add_error_gets_a_line(cache_path):
    music = FakeMusic({"Road": [A, C]}, fail_add={"A": "first", "C": "second"})
    result = invoke(music, ["bass", "sort", "Road", "--no-review"], cache_path)
    assert result.exit_code == 0, result.output
    assert "Couldn't add Tool %s Schism to %s: first" % (DASH, DROP_D) in result.output
    assert "Couldn't add Opeth %s Deliverance to %s: second" % (DASH, EB_STD) in result.output
    assert result.output.count("Couldn't add") == 2


def test_no_add_error_lines_without_errors(cache_path):
    result = invoke(FakeMusic({"Road": [A]}), ["bass", "sort", "Road"], cache_path)
    assert "Couldn't add" not in result.output


# -------------------------------------------------------------- EOF at review prompt


def test_review_eof_exits_cleanly_and_keeps_queue(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result = invoke(FakeMusic(), ["bass", "review"], cache_path, input="")
    assert result.exit_code == 0, result.output
    assert "Aborted" not in result.output
    assert len(_queued(cache_path)) == 2
    assert _entry(cache_path, "Tool", "Schism") is None


def test_review_eof_after_an_answer_keeps_answers_so_far(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", [])])
    result = invoke(FakeMusic(), ["bass", "review"], cache_path, input="Drop C\n")
    assert result.exit_code == 0, result.output
    assert "Aborted" not in result.output
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("C G C F"), "manual", True)
    assert _queued(cache_path) == [("Opeth", "Deliverance")]


def test_review_eof_after_invalid_answer(cache_path):
    _queue(cache_path, [("Tool", "Schism", CANDS)])
    result = invoke(FakeMusic(), ["bass", "review"], cache_path, input="banana\n")
    assert result.exit_code == 0, result.output
    assert "Aborted" not in result.output
    assert _queued(cache_path) == [("Tool", "Schism")]


def test_sort_review_eof_exits_cleanly(cache_path):
    music = FakeMusic({"Road": [A, B]})
    sources = [FakeSource("s", {("Tool", "Schism"): make_match("D A D G", "ug-bass")})]
    result = invoke(music, ["bass", "sort", "Road", "--review"], cache_path, sources, input="")
    assert result.exit_code == 0, result.output
    assert "Aborted" not in result.output
    assert music.playlists[DROP_D] == [A]
    assert _queued(cache_path) == [("Nobody", "Nothing")]


def test_sort_review_eof_keeps_answers_given_so_far(cache_path):
    music = FakeMusic({"Road": [A, B, C]})
    sources = [FakeSource("s", {("Tool", "Schism"): make_match("D A D G", "ug-bass")})]
    result = invoke(
        music, ["bass", "sort", "Road", "--review"], cache_path, sources, input="Drop D\n"
    )
    assert result.exit_code == 0, result.output
    assert "Aborted" not in result.output
    assert _entry(cache_path, "Nobody", "Nothing") == Entry(T("D A D G"), "manual", True)
    assert _entry(cache_path, "Opeth", "Deliverance") is None
    assert music.playlists[DROP_D] == [A, B]


# ------------------------------------------------- review after sort matches by song


def test_review_after_sort_matches_normalised_titles(cache_path):
    remaster = make_track("R", "Tool", "Schism (Remastered)")
    _queue(
        cache_path,
        [("Tool", "Schism", CANDS), ("Opeth", "Deliverance", []), ("Rush", "YYZ", [])],
    )
    music = FakeMusic({"Road": [remaster]})
    result = invoke(
        music,
        ["bass", "sort", "Road", "--review"],
        cache_path,
        [FakeSource("s")],
        input="Drop D\n",
    )
    assert result.exit_code == 0, result.output
    assert "Opeth" not in result.output
    assert "Rush" not in result.output
    assert _entry(cache_path, "Tool", "Schism") == Entry(T("D A D G"), "manual", True)
    assert music.playlists[DROP_D] == [remaster]
    assert set(_queued(cache_path)) == {("Opeth", "Deliverance"), ("Rush", "YYZ")}


def test_review_after_sort_question_counts_only_this_playlist(cache_path):
    _queue(cache_path, [("Opeth", "Deliverance", []), ("Rush", "YYZ", [])])
    music = FakeMusic({"Road": [make_track("R", "Tool", "Schism (Remastered)"), C]})
    _queue(cache_path, [("Tool", "Schism", [])])
    result = invoke(music, ["bass", "sort", "Road"], cache_path, [FakeSource("s")], input="n\n")
    assert result.exit_code == 0, result.output
    assert "Review 2 songs now?" in result.output
