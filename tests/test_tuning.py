from __future__ import annotations

import pytest

from bass_sort.tuning import Tuning, TuningParseError, from_midi, parse_name, parse_note_names

DASH = "–"


def test_pitch_classes_and_string_count():
    assert Tuning((4, 9, 2, 7)).string_count == 4
    assert Tuning((11, 4, 9, 2, 7)).string_count == 5


def test_enharmonic_equality():
    assert parse_note_names("D# G# C# F#") == parse_note_names("Eb Ab Db Gb")


@pytest.mark.parametrize(
    "pcs,expected",
    [
        ((4, 9, 2, 7), "E Standard"),
        ((2, 9, 2, 7), "Drop D"),
        ((2, 7, 0, 5), "D Standard"),
        ((0, 7, 0, 5), "Drop C"),
        ((3, 8, 1, 6), "Eb Standard"),
        ((1, 6, 11, 4), "Db Standard"),
        ((11, 4, 9, 2), "B Standard"),
        ((11, 4, 9, 2, 7), "B Standard"),
        ((11, 4, 9, 2, 7, 0), "B Standard"),
        ((9, 4, 9, 2, 7), "Drop A"),
        ((2, 9, 2, 6), "D A D Gb"),
        ((1, 8, 3, 10), "Db Ab Eb Bb"),
        # Drop tunings spell the root with sharps.
        ((1, 8, 1, 6), "Drop C#"),
        ((10, 5, 10, 3), "Drop A#"),
        ((6, 1, 6, 11), "Drop F#"),
        ((8, 3, 8, 1), "Drop G#"),
        ((3, 10, 3, 8), "Drop D#"),
        ((1, 8, 1, 6, 11), "Drop C#"),
    ],
)
def test_name(pcs, expected):
    assert Tuning(pcs).name == expected


@pytest.mark.parametrize(
    "notes,expected",
    [
        ("C# G# C# F#", "Drop C#"),
        ("Db Ab Db Gb", "Drop C#"),
        ("A# F A# D#", "Drop A#"),
        ("F# C# F# B", "Drop F#"),
        ("G# D# G# C#", "Drop G#"),
        ("D A D G", "Drop D"),
        ("C G C F", "Drop C"),
        ("A E A D G", "Drop A"),
        ("D# G# C# F#", "Eb Standard"),
        ("C# F# B E", "Db Standard"),
        ("D A D Gb", "D A D Gb"),
    ],
)
def test_name_from_notes(notes, expected):
    assert parse_note_names(notes).name == expected


def test_playlist_names():
    assert Tuning((2, 9, 2, 7)).playlist_name == "Bass %s Drop D" % DASH
    assert Tuning((11, 4, 9, 2, 7)).playlist_name == "Bass 5-String %s B Standard" % DASH
    assert Tuning((11, 4, 9, 2, 7, 0)).playlist_name == "Bass 6-String %s B Standard" % DASH


def test_playlist_names_for_sharp_drop():
    assert Tuning((1, 8, 1, 6)).playlist_name == "Bass %s Drop C#" % DASH
    assert Tuning((1, 8, 1, 6, 11)).playlist_name == "Bass 5-String %s Drop C#" % DASH


def test_playlist_names_distinguish_string_counts():
    assert Tuning((11, 4, 9, 2)).playlist_name != Tuning((11, 4, 9, 2, 7)).playlist_name


def test_enharmonic_spellings_share_playlist():
    a = parse_note_names("D# G# C# F#").playlist_name
    b = parse_note_names("Eb Ab Db Gb").playlist_name
    assert a == b == "Bass %s Eb Standard" % DASH


def test_enharmonic_drop_spellings_share_playlist():
    a = parse_note_names("C# G# C# F#").playlist_name
    b = parse_note_names("Db Ab Db Gb").playlist_name
    assert a == b == "Bass %s Drop C#" % DASH


@pytest.mark.parametrize(
    "text,pcs",
    [
        ("D A D G", (2, 9, 2, 7)),
        ("D, A, D, G", (2, 9, 2, 7)),
        ("DADG", (2, 9, 2, 7)),
        ("dadg", (2, 9, 2, 7)),
        ("d a d g", (2, 9, 2, 7)),
        ("EbAbDbGb", (3, 8, 1, 6)),
        ("D#G#C#F#", (3, 8, 1, 6)),
        ("E1 A1 D2 G2", (4, 9, 2, 7)),
        ("B E A D G", (11, 4, 9, 2, 7)),
        ("B E A D G C", (11, 4, 9, 2, 7, 0)),
    ],
)
def test_parse_note_names(text, pcs):
    assert parse_note_names(text) == Tuning(pcs)


@pytest.mark.parametrize(
    "text", ["", "   ", "H A D G", "E A D", "E A D G B E A", "hello world", "E A D X"]
)
def test_parse_note_names_rejects(text):
    with pytest.raises(TuningParseError):
        parse_note_names(text)


def test_parse_error_is_value_error():
    assert issubclass(TuningParseError, ValueError)


def test_from_midi():
    assert from_midi([28, 33, 38, 43]) == Tuning((4, 9, 2, 7))
    assert from_midi([26, 33, 38, 43]) == Tuning((2, 9, 2, 7))
    assert from_midi([23, 28, 33, 38, 43]) == Tuning((11, 4, 9, 2, 7))
    assert from_midi([23, 28, 33, 38, 43, 48]).string_count == 6


def test_from_midi_sharp_drop_name():
    assert from_midi([25, 32, 37, 42]).name == "Drop C#"


@pytest.mark.parametrize("notes", [[], [28, 33, 38], [28, 33, 38, 43, 48, 53, 58]])
def test_from_midi_wrong_count(notes):
    with pytest.raises(TuningParseError):
        from_midi(notes)


@pytest.mark.parametrize(
    "text,pcs",
    [
        ("Drop D", (2, 9, 2, 7)),
        ("drop d", (2, 9, 2, 7)),
        ("E Standard", (4, 9, 2, 7)),
        ("eb standard", (3, 8, 1, 6)),
        ("D# Standard", (3, 8, 1, 6)),
        ("Standard", (4, 9, 2, 7)),
        ("5-string B Standard", (11, 4, 9, 2, 7)),
        ("5 string B Standard", (11, 4, 9, 2, 7)),
        ("6-string B Standard", (11, 4, 9, 2, 7, 0)),
        ("5-string Drop D", (2, 9, 2, 7, 0)),
        ("Drop C#", (1, 8, 1, 6)),
        ("drop c#", (1, 8, 1, 6)),
        ("Drop Db", (1, 8, 1, 6)),
        ("5-string Drop C#", (1, 8, 1, 6, 11)),
        ("D A D G", (2, 9, 2, 7)),
        ("EbAbDbGb", (3, 8, 1, 6)),
    ],
)
def test_parse_name(text, pcs):
    assert parse_name(text) == Tuning(pcs)


@pytest.mark.parametrize("text", ["", "banana", "Drop", "Drop H", "7-string E Standard"])
def test_parse_name_rejects(text):
    with pytest.raises(TuningParseError):
        parse_name(text)


# ------------------------------------------- 6-string guitar tunings reduce to 4 strings


@pytest.mark.parametrize(
    "text,pcs,name",
    [
        ("E A D G B E", (4, 9, 2, 7), "E Standard"),
        ("D A D G B E", (2, 9, 2, 7), "Drop D"),
        ("Eb Ab Db Gb Bb Eb", (3, 8, 1, 6), "Eb Standard"),
        ("C# G# C# F# A# D#", (1, 8, 1, 6), "Drop C#"),
        ("EADGBE", (4, 9, 2, 7), "E Standard"),
        ("E, A, D, G, B, E", (4, 9, 2, 7), "E Standard"),
    ],
)
def test_parse_note_names_reduces_guitar_tuning(text, pcs, name):
    t = parse_note_names(text)
    assert t == Tuning(pcs)
    assert t.string_count == 4
    assert t.name == name


def test_guitar_tuning_playlist_name():
    assert parse_note_names("E A D G B E").playlist_name == "Bass %s E Standard" % DASH


def test_from_midi_reduces_guitar_tuning():
    t = from_midi([40, 45, 50, 55, 59, 64])
    assert t == Tuning((4, 9, 2, 7))
    assert t.string_count == 4
    assert t.name == "E Standard"


def test_from_midi_drop_d_guitar_tuning_reduces():
    t = from_midi([38, 45, 50, 55, 59, 64])
    assert t.string_count == 4
    assert t.name == "Drop D"


def test_six_string_bass_kept():
    t = parse_note_names("B E A D G C")
    assert t.string_count == 6
    assert t.name == "B Standard"
    assert t.playlist_name == "Bass 6-String %s B Standard" % DASH
    assert from_midi([23, 28, 33, 38, 43, 48]).string_count == 6


def test_six_string_without_major_third_kept():
    t = parse_note_names("D A D G A D")
    assert t.string_count == 6
    assert t == Tuning((2, 9, 2, 7, 9, 2))


def test_four_and_five_string_never_reduced():
    assert parse_note_names("E A D G").string_count == 4
    assert parse_note_names("B E A D G").string_count == 5
    assert from_midi([23, 28, 33, 38, 43]).string_count == 5


def test_direct_construction_not_reduced():
    assert Tuning((4, 9, 2, 7, 11, 4)).string_count == 6


def test_parse_name_reduces_guitar_tuning():
    assert parse_name("EADGBE") == Tuning((4, 9, 2, 7))
    assert parse_name("E A D G B E") == Tuning((4, 9, 2, 7))
    assert parse_name("D A D G B E").name == "Drop D"


def test_parse_name_six_string_standard_still_six():
    assert parse_name("6-string B Standard").string_count == 6
