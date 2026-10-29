from __future__ import annotations

import pytest
from conftest import T

from tune_sort.tuning import (
    INSTRUMENTS,
    STRING_RANGE,
    Tuning,
    TuningParseError,
    from_midi,
    from_pitch_classes,
    parse_name,
    parse_note_names,
)

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


# ----------------------------------------------------------------------- notes


@pytest.mark.parametrize(
    "pcs,expected",
    [
        ((4, 9, 2, 7), "E A D G"),
        ((2, 9, 2, 7), "D A D G"),
        ((1, 8, 1, 6), "C# G# C# F#"),
        ((3, 8, 1, 6), "Eb Ab Db Gb"),
        ((11, 4, 9, 2, 7), "B E A D G"),
        ((11, 4, 9, 2, 7, 0), "B E A D G C"),
        ((9, 4, 9, 2, 7), "A E A D G"),
        ((2, 9, 2, 6), "D A D Gb"),
        ((10, 5, 10, 3), "A# F A# D#"),
        ((0, 7, 0, 5), "C G C F"),
        ((1, 6, 11, 4), "Db Gb B E"),
        ((6, 11, 4, 9), "F# B E A"),
    ],
)
def test_notes(pcs, expected):
    assert Tuning(pcs).notes == expected


def test_notes_spelling_follows_name_not_input():
    assert parse_note_names("Db Ab Db Gb").notes == "C# G# C# F#"
    assert parse_note_names("D# G# C# F#").notes == "Eb Ab Db Gb"
    assert parse_note_names("D A D F#").notes == "D A D Gb"


def test_notes_from_name_and_midi():
    assert parse_name("5-string B Standard").notes == "B E A D G"
    assert parse_name("6-string B Standard").notes == "B E A D G C"
    assert parse_name("5-string Drop A").notes == "A E A D G"
    assert from_midi([26, 33, 38, 43]).notes == "D A D G"


# ---------------------------------------------------------- bass F# Standard naming


def test_bass_f_sharp_standard_uses_sharp_root():
    assert Tuning((6, 11, 4, 9)).name == "F# Standard"
    assert Tuning((6, 11, 4, 9, 2)).name == "F# Standard"
    assert Tuning((6, 11, 4, 9)).playlist_name == "Bass %s F# Standard" % DASH


def test_bass_other_standard_roots_still_flats():
    assert Tuning((3, 8, 1, 6)).name == "Eb Standard"
    assert Tuning((1, 6, 11, 4)).name == "Db Standard"
    assert Tuning((10, 3, 8, 1)).name == "Bb Standard"


# ================================================================== guitar mode


def test_instrument_constants():
    assert INSTRUMENTS == ("bass", "guitar")
    assert STRING_RANGE == {"bass": (4, 6), "guitar": (6, 8)}


def test_instrument_defaults_to_bass():
    assert Tuning((4, 9, 2, 7)).instrument == "bass"
    assert Tuning((4, 9, 2, 7, 11, 4), "guitar").instrument == "guitar"


def test_tunings_of_different_instruments_never_equal():
    pcs = (4, 9, 2, 7, 11, 4)
    assert Tuning(pcs, "guitar") != Tuning(pcs)
    assert Tuning(pcs, "guitar") == Tuning(pcs, "guitar")


def test_parse_functions_return_requested_instrument():
    assert parse_note_names("E A D G").instrument == "bass"
    assert parse_note_names("E A D G B E", "guitar").instrument == "guitar"
    assert from_midi([28, 33, 38, 43]).instrument == "bass"
    assert from_midi([40, 45, 50, 55, 59, 64], "guitar").instrument == "guitar"
    assert parse_name("Drop D").instrument == "bass"
    assert parse_name("Drop D", "guitar").instrument == "guitar"
    assert from_pitch_classes((4, 9, 2, 7, 11, 4), "guitar").instrument == "guitar"


# (note names, name, notes, playlist name)
GUITAR_CASES = [
    ("E A D G B E", "E Standard", "E A D G B E", "Guitar %s E Standard" % DASH),
    ("Eb Ab Db Gb Bb Eb", "Eb Standard", "Eb Ab Db Gb Bb Eb", "Guitar %s Eb Standard" % DASH),
    ("D# G# C# F# A# D#", "Eb Standard", "Eb Ab Db Gb Bb Eb", "Guitar %s Eb Standard" % DASH),
    ("D G C F A D", "D Standard", "D G C F A D", "Guitar %s D Standard" % DASH),
    ("B E A D G B E", "B Standard", "B E A D G B E", "Guitar 7-String %s B Standard" % DASH),
    (
        "F# B E A D G B E",
        "F# Standard",
        "F# B E A D G B E",
        "Guitar 8-String %s F# Standard" % DASH,
    ),
    ("D A D G B E", "Drop D", "D A D G B E", "Guitar %s Drop D" % DASH),
    ("C# G# C# F# A# D#", "Drop C#", "C# G# C# F# A# D#", "Guitar %s Drop C#" % DASH),
    ("Db Ab Db Gb Bb Eb", "Drop C#", "C# G# C# F# A# D#", "Guitar %s Drop C#" % DASH),
    ("C G C F A D", "Drop C", "C G C F A D", "Guitar %s Drop C" % DASH),
    ("A E A D G B E", "Drop A", "A E A D G B E", "Guitar 7-String %s Drop A" % DASH),
    ("D A D G A D", "DADGAD", "D A D G A D", "Guitar %s DADGAD" % DASH),
    ("D A D F# A D", "Open D", "D A D F# A D", "Guitar %s Open D" % DASH),
    ("D G D G B D", "Open G", "D G D G B D", "Guitar %s Open G" % DASH),
    ("E B E G# B E", "Open E", "E B E G# B E", "Guitar %s Open E" % DASH),
    ("E A E A C# E", "Open A", "E A E A C# E", "Guitar %s Open A" % DASH),
    ("C G C G C E", "Open C", "C G C G C E", "Guitar %s Open C" % DASH),
    ("E A D Gb B E", "E A D Gb B E", "E A D Gb B E", "Guitar %s E A D Gb B E" % DASH),
]


@pytest.mark.parametrize("text,name,notes,playlist", GUITAR_CASES)
def test_guitar_name_notes_and_playlist(text, name, notes, playlist):
    t = T(text, "guitar")
    assert t.name == name
    assert t.notes == notes
    assert t.playlist_name == playlist


def test_guitar_string_counts():
    assert T("E A D G B E", "guitar").string_count == 6
    assert T("B E A D G B E", "guitar").string_count == 7
    assert T("F# B E A D G B E", "guitar").string_count == 8


def test_guitar_enharmonic_spellings_share_playlist():
    a = T("D# G# C# F# A# D#", "guitar").playlist_name
    b = T("Eb Ab Db Gb Bb Eb", "guitar").playlist_name
    assert a == b


@pytest.mark.parametrize(
    "text,pcs",
    [
        ("E A D G B E", (4, 9, 2, 7, 11, 4)),
        ("EADGBE", (4, 9, 2, 7, 11, 4)),
        ("B E A D G B E", (11, 4, 9, 2, 7, 11, 4)),
        ("F# B E A D G B E", (6, 11, 4, 9, 2, 7, 11, 4)),
    ],
)
def test_guitar_parse_note_names_keeps_string_count(text, pcs):
    t = parse_note_names(text, "guitar")
    assert t == Tuning(pcs, "guitar")
    assert t.string_count == len(pcs)


@pytest.mark.parametrize(
    "text",
    ["", "E A D G", "B E A D G", "E A D G B E A D G", "banana", "E A D G B X"],
)
def test_guitar_parse_note_names_rejects(text):
    with pytest.raises(TuningParseError):
        parse_note_names(text, "guitar")


def test_guitar_from_midi():
    t = from_midi([40, 45, 50, 55, 59, 64], "guitar")
    assert t == Tuning((4, 9, 2, 7, 11, 4), "guitar")
    assert t.name == "E Standard"
    assert from_midi([38, 45, 50, 55, 59, 64], "guitar").name == "Drop D"
    assert from_midi([35, 40, 45, 50, 55, 59, 64], "guitar").string_count == 7


@pytest.mark.parametrize("notes", [[], [28, 33, 38, 43], [28, 33, 38, 43, 47], list(range(30, 39))])
def test_guitar_from_midi_wrong_count(notes):
    with pytest.raises(TuningParseError):
        from_midi(notes, "guitar")


def test_guitar_from_pitch_classes_keeps_six_strings():
    t = from_pitch_classes((4, 9, 2, 7, 11, 4), "guitar")
    assert t == Tuning((4, 9, 2, 7, 11, 4), "guitar")
    assert t.string_count == 6


@pytest.mark.parametrize(
    "text,pcs",
    [
        ("Drop D", (2, 9, 2, 7, 11, 4)),
        ("drop d", (2, 9, 2, 7, 11, 4)),
        ("Standard", (4, 9, 2, 7, 11, 4)),
        ("E Standard", (4, 9, 2, 7, 11, 4)),
        ("eb standard", (3, 8, 1, 6, 10, 3)),
        ("D# Standard", (3, 8, 1, 6, 10, 3)),
        ("7-string B Standard", (11, 4, 9, 2, 7, 11, 4)),
        ("8-string F# Standard", (6, 11, 4, 9, 2, 7, 11, 4)),
        ("7-string Drop A", (9, 4, 9, 2, 7, 11, 4)),
        ("DADGAD", (2, 9, 2, 7, 9, 2)),
        ("Open G", (2, 7, 2, 7, 11, 2)),
        ("open d", (2, 9, 2, 6, 9, 2)),
        ("Open E", (4, 11, 4, 8, 11, 4)),
        ("Open A", (4, 9, 4, 9, 1, 4)),
        ("Open C", (0, 7, 0, 7, 0, 4)),
        ("DADGBE", (2, 9, 2, 7, 11, 4)),
        ("D A D G B E", (2, 9, 2, 7, 11, 4)),
    ],
)
def test_guitar_parse_name(text, pcs):
    t = parse_name(text, "guitar")
    assert t == Tuning(pcs, "guitar")
    assert t.instrument == "guitar"


def test_guitar_parse_name_dadgbe_is_drop_d():
    assert parse_name("DADGBE", "guitar").name == "Drop D"


@pytest.mark.parametrize("text", ["", "banana", "Drop", "E A D G", "5-string E Standard"])
def test_guitar_parse_name_rejects(text):
    with pytest.raises(TuningParseError):
        parse_name(text, "guitar")


def test_bass_parse_name_meaning_unchanged_with_explicit_instrument():
    assert parse_name("Drop D", "bass") == Tuning((2, 9, 2, 7))
    assert parse_name("Standard", "bass") == Tuning((4, 9, 2, 7))
    assert parse_name("EADGBE", "bass") == Tuning((4, 9, 2, 7))
