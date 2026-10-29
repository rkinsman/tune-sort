"""Bass tunings: parsing, enharmonic normalisation and naming."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# One spelling per pitch class, so enharmonic tunings get the same name. Drop tunings are
# conventionally named with sharps (Drop C#), everything else with flats (Eb Standard).
FLAT_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE = re.compile(r"([A-Ga-g])([#b♯♭]?)\d*")
MIN_STRINGS = 4
MAX_STRINGS = 6
FOURTH = 5
FIFTH = 7
MAJOR_THIRD = 4  # between a guitar's G and B strings


class TuningParseError(ValueError):
    pass


@dataclass(frozen=True)
class Tuning:
    """A tuning as pitch classes (0 = C ... 11 = B), lowest string first.

    Pitch classes make enharmonic spellings equal: D# and Eb are both 3.
    """

    pitch_classes: tuple[int, ...]

    @property
    def string_count(self) -> int:
        return len(self.pitch_classes)

    @property
    def name(self) -> str:
        """Canonical name, e.g. "E Standard", "Drop D", "Eb Standard", "Drop C#", or "D A D Gb".

        Drop tunings spell their root with sharps (Drop C#); standard tunings and note
        lists use flats (Eb Standard, D A D Gb)."""
        pcs = self.pitch_classes
        gaps = [(b - a) % 12 for a, b in zip(pcs, pcs[1:], strict=False)]
        if gaps and all(g == FOURTH for g in gaps):
            return f"{FLAT_NAMES[pcs[0]]} Standard"
        if gaps and gaps[0] == FIFTH and all(g == FOURTH for g in gaps[1:]):
            return f"Drop {SHARP_NAMES[pcs[0]]}"
        return " ".join(FLAT_NAMES[pc] for pc in pcs)

    @property
    def playlist_name(self) -> str:
        """e.g. "Bass – Drop D", "Bass 5-String – B Standard", "Bass 6-String – B Standard"."""
        if self.string_count == 4:
            return f"Bass – {self.name}"
        return f"Bass {self.string_count}-String – {self.name}"


def _checked(pcs: list[int]) -> Tuning:
    if not MIN_STRINGS <= len(pcs) <= MAX_STRINGS:
        raise TuningParseError(f"expected {MIN_STRINGS}-{MAX_STRINGS} strings, got {len(pcs)}")
    if len(pcs) == 6 and (pcs[4] - pcs[3]) % 12 == MAJOR_THIRD:
        # A guitar tuning: the bass plays the lowest four strings.
        pcs = pcs[:4]
    return Tuning(tuple(pcs))


def parse_note_names(text: str) -> Tuning:
    """Parse note names listed lowest string first, e.g. "D A D G", "DADG", "Eb Ab Db Gb".

    A 6-string guitar tuning (a major third between the 4th and 5th strings, e.g.
    E A D G B E or D A D G B E) is reduced to its lowest four strings, since the bass
    plays those: E A D G B E becomes E Standard. A 6-string bass is all fourths and
    is kept as it is."""
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
    return _checked(pcs)


def from_pitch_classes(pitch_classes: Iterable[int]) -> Tuning:
    """Build a tuning from stored pitch classes, applying the guitar-tuning reduction."""
    return _checked([pc % 12 for pc in pitch_classes])


def from_midi(notes: Iterable[int]) -> Tuning:
    """Build a tuning from MIDI note numbers listed lowest string first. 6-string guitar
    tunings are reduced to their lowest four strings, as in parse_note_names."""
    return _checked([n % 12 for n in notes])


_NAMED = re.compile(
    r"^(?:(?P<strings>\d+)[\s-]*string\s+)?"
    r"(?:(?P<drop>drop)\s+(?P<droot>[a-g][#b]?)|(?:(?P<sroot>[a-g][#b]?)\s+)?standard)$"
)


def parse_name(name: str) -> Tuning:
    """Parse a tuning name typed by the user ("Drop D", "eb standard", "5-string B Standard")
    or a list of note names. Raises TuningParseError if not understood."""
    m = _NAMED.match(" ".join(name.strip().lower().split()))
    if m is None:
        return parse_note_names(name)
    strings = int(m.group("strings") or 4)
    root_text = m.group("droot") or m.group("sroot") or "e"
    root = (_LETTERS[root_text[0].upper()] + {"#": 1, "b": -1}.get(root_text[1:], 0)) % 12
    first_gap = FIFTH if m.group("drop") else FOURTH
    pcs = [root]
    for i in range(strings - 1):
        pcs.append((pcs[-1] + (first_gap if i == 0 else FOURTH)) % 12)
    return _checked(pcs)
