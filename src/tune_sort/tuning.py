"""Bass and guitar tunings: parsing, enharmonic normalisation and naming.

Guitar naming rules (6-8 strings, pitch classes lowest first):
- "<root> Standard": fourths with one major third between the 2nd- and 3rd-highest
  strings, e.g. E A D G B E, Eb Ab Db Gb Bb Eb, B E A D G B E (7), F# B E A D G B E (8).
- "Drop <root>" (sharps): a fifth at the bottom, then the standard pattern, e.g.
  D A D G B E, C# G# C# F# A# D#, A E A D G B E (7).
- 6-string open tunings, matched exactly: DADGAD (D A D G A D), Open D (D A D F# A D),
  Open G (D G D G B D), Open E (E B E G# B E), Open A (E A E A C# E),
  Open C (C G C G C E).
- Anything else: the notes, flats.
Standard roots are spelled with flats except F# ("F# Standard", for both instruments,
since that is what 8-string players call it). Notes (Tuning.notes) use sharps for drop
tunings, open tunings and F# Standard, flats otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Optional

# One spelling per pitch class, so enharmonic tunings get the same name. Drop tunings are
# conventionally named with sharps (Drop C#), everything else with flats (Eb Standard).
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
F_SHARP = 6
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE = re.compile(r"([A-Ga-g])([#b♯♭]?)\d*")
FOURTH = 5
FIFTH = 7
MAJOR_THIRD = 4  # between a guitar's G and B strings


class TuningParseError(ValueError):
    pass


Instrument = Literal["bass", "guitar"]
INSTRUMENTS: tuple[Instrument, ...] = ("bass", "guitar")
STRING_RANGE = {"bass": (4, 6), "guitar": (6, 8)}  # strings accepted when parsing
DEFAULT_STRINGS = {"bass": 4, "guitar": 6}  # not shown in playlist names
PLAYLIST_PREFIX = {"bass": "Bass", "guitar": "Guitar"}

# 6-string guitar open tunings, matched exactly.
OPEN_TUNINGS: dict[tuple[int, ...], str] = {
    (2, 9, 2, 7, 9, 2): "DADGAD",
    (2, 9, 2, 6, 9, 2): "Open D",
    (2, 7, 2, 7, 11, 2): "Open G",
    (4, 11, 4, 8, 11, 4): "Open E",
    (4, 9, 4, 9, 1, 4): "Open A",
    (0, 7, 0, 7, 0, 4): "Open C",
}
_OPEN_BY_NAME = {name.lower(): pcs for pcs, name in OPEN_TUNINGS.items()}


def _standard_gaps(instrument: Instrument, strings: int) -> list[int]:
    """Bass: all fourths. Guitar: fourths with a major third below the highest string."""
    gaps = [FOURTH] * (strings - 1)
    if instrument == "guitar" and strings >= 3:
        gaps[-2] = MAJOR_THIRD
    return gaps


@dataclass(frozen=True)
class Tuning:
    """A tuning as pitch classes (0 = C ... 11 = B), lowest string first, for an
    instrument. Tunings for different instruments are never equal.

    Pitch classes make enharmonic spellings equal: D# and Eb are both 3.
    """

    pitch_classes: tuple[int, ...]
    instrument: Instrument = "bass"

    @property
    def string_count(self) -> int:
        return len(self.pitch_classes)

    @property
    def name(self) -> str:
        """Canonical name, e.g. "E Standard", "Drop D", "Eb Standard", "Drop C#", "Open G",
        or the notes, e.g. "D A D Gb". See the module docstring for the rules."""
        root = self.pitch_classes[0]
        if self._is_standard():
            spelling = SHARP_NAMES if root == F_SHARP else FLAT_NAMES
            return f"{spelling[root]} Standard"
        if self._is_drop():
            return f"Drop {SHARP_NAMES[root]}"
        return self._open_name() or self.notes

    @property
    def notes(self) -> str:
        """The string notes lowest first, spelled as in `name`: sharps for drop tunings,
        open tunings and F# Standard, flats otherwise, e.g. "C# G# C# F#" for Drop C#,
        "Eb Ab Db Gb" for Eb Standard."""
        sharp = (
            self._is_drop()
            or self._open_name() is not None
            or (self._is_standard() and self.pitch_classes[0] == F_SHARP)
        )
        spelling = SHARP_NAMES if sharp else FLAT_NAMES
        return " ".join(spelling[pc] for pc in self.pitch_classes)

    @property
    def playlist_name(self) -> str:
        """Bass: "Bass – Drop D" (4 strings), "Bass 5-String – B Standard", "Bass 6-String – …".
        Guitar: "Guitar – Drop D" (6 strings), "Guitar 7-String – B Standard",
        "Guitar 8-String – F# Standard"."""
        prefix = PLAYLIST_PREFIX[self.instrument]
        if self.string_count == DEFAULT_STRINGS[self.instrument]:
            return f"{prefix} – {self.name}"
        return f"{prefix} {self.string_count}-String – {self.name}"

    def _gaps(self) -> list[int]:
        pcs = self.pitch_classes
        return [(b - a) % 12 for a, b in zip(pcs, pcs[1:], strict=False)]

    def _is_standard(self) -> bool:
        gaps = self._gaps()
        return bool(gaps) and gaps == _standard_gaps(self.instrument, self.string_count)

    def _is_drop(self) -> bool:
        gaps = self._gaps()
        standard = _standard_gaps(self.instrument, self.string_count)
        return bool(gaps) and gaps[0] == FIFTH and gaps[1:] == standard[1:]

    def _open_name(self) -> Optional[str]:
        if self.instrument != "guitar":
            return None
        return OPEN_TUNINGS.get(self.pitch_classes)


def _checked(pcs: list[int], instrument: Instrument = "bass") -> Tuning:
    low, high = STRING_RANGE[instrument]
    if not low <= len(pcs) <= high:
        raise TuningParseError(f"expected {low}-{high} strings for {instrument}, got {len(pcs)}")
    if instrument == "bass" and len(pcs) == 6 and (pcs[4] - pcs[3]) % 12 == MAJOR_THIRD:
        # A guitar tuning: the bass plays the lowest four strings.
        pcs = pcs[:4]
    return Tuning(tuple(pcs), instrument)


def parse_note_names(text: str, instrument: Instrument = "bass") -> Tuning:
    """Parse note names listed lowest string first, e.g. "D A D G", "DADG", "Eb Ab Db Gb".

    A 6-string guitar tuning (a major third between the 4th and 5th strings, e.g.
    E A D G B E or D A D G B E) is reduced to its lowest four strings, since the bass
    plays those: E A D G B E becomes E Standard. A 6-string bass is all fourths and
    is kept as it is. The guitar reduction applies to bass only; for guitar the notes are
    kept. The string count must be in STRING_RANGE[instrument]."""
    compact = re.sub(r"[\s,]+", "", text)
    if not compact:
        raise TuningParseError("no notes given")
    pcs: list[int] = []
    pos = 0
    while pos < len(compact):
        m = _NOTE.match(compact, pos)
        if not m:
            raise TuningParseError(f"not a note list: {text!r}")
        letter, accidental = m.group(1).upper(), m.group(2)
        pc = _LETTERS[letter]
        if accidental in ("#", "♯"):
            pc += 1
        elif accidental in ("b", "♭"):
            pc -= 1
        pcs.append(pc % 12)
        pos = m.end()
    return _checked(pcs, instrument)


def from_pitch_classes(pitch_classes: Iterable[int], instrument: Instrument = "bass") -> Tuning:
    """Build a tuning from stored pitch classes, applying the guitar-tuning reduction."""
    return _checked([pc % 12 for pc in pitch_classes], instrument)


def from_midi(notes: Iterable[int], instrument: Instrument = "bass") -> Tuning:
    """Build a tuning from MIDI note numbers listed lowest string first. 6-string guitar
    tunings are reduced to their lowest four strings, as in parse_note_names."""
    return _checked([n % 12 for n in notes], instrument)


_NAMED = re.compile(
    r"^(?:(?P<strings>\d+)[\s-]*string\s+)?"
    r"(?:(?P<drop>drop)\s+(?P<droot>[a-g][#b]?)|(?:(?P<sroot>[a-g][#b]?)\s+)?standard)$"
)


def is_tuning_playlist(name: str, instrument: Instrument) -> bool:
    """True if `name` has the shape of one of the instrument's tuning playlist names:
    "<Prefix> – <tuning>" or "<Prefix> <N>-String – <tuning>" (en dash), e.g. "Bass – Drop D"
    or "Guitar 7-String – B Standard"."""
    prefix = re.escape(PLAYLIST_PREFIX[instrument])
    return re.fullmatch(prefix + r"( [0-9]+-String)? \u2013 \S.*", name) is not None


def parse_name(name: str, instrument: Instrument = "bass") -> Tuning:
    """Parse a tuning name typed by the user ("Drop D", "eb standard", "5-string B Standard")
    or a list of note names. Raises TuningParseError if not understood.

    For guitar the default string count is 6, standard and drop tunings follow the guitar
    pattern ("Drop D" = D A D G B E, "7-string B Standard" = B E A D G B E), and the open
    tuning names are accepted ("DADGAD", "Open G", "open d")."""
    text = " ".join(name.strip().lower().split())
    if instrument == "guitar" and text in _OPEN_BY_NAME:
        return Tuning(_OPEN_BY_NAME[text], "guitar")
    m = _NAMED.match(text)
    if m is None:
        return parse_note_names(name, instrument)
    strings = int(m.group("strings") or DEFAULT_STRINGS[instrument])
    root_text = m.group("droot") or m.group("sroot") or "e"
    root = (_LETTERS[root_text[0].upper()] + {"#": 1, "b": -1}.get(root_text[1:], 0)) % 12
    gaps = _standard_gaps(instrument, strings)
    if m.group("drop") and gaps:
        gaps[0] = FIFTH
    pcs = [root]
    for gap in gaps:
        pcs.append((pcs[-1] + gap) % 12)
    return _checked(pcs, instrument)
