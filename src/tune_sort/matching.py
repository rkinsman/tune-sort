"""Deciding whether a tab site's song is the same song as an Apple Music track."""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Bracketed or dashed suffixes that name the same recording.
_SAME_RECORDING = re.compile(
    r"remaster|deluxe|feat\.?|ft\.|featuring|mono|stereo|album version|single version"
    r"|radio edit|bonus track|expanded|anniversary|edition",
    re.IGNORECASE,
)
_BRACKETED = re.compile(r"\s*[(\[]([^)\]]*)[)\]]")
# The text after the last spaced dash: "Of Matter - Retrospect - 2013 Remaster".
_DASHED = re.compile(r"\s+[-–—]\s+((?:(?!\s[-–—]\s).)*)$")
_VERSION = re.compile(
    r"\b(live|acoustic|demo|remix|mix|edit|version|remaster\w*|mono|stereo|instrumental"
    r"|unplugged|cover|karaoke)\b",
    re.IGNORECASE,
)


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"['’`]", "", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def normalise_title(title: str) -> str:
    """Lowercase, drop punctuation, and drop bracketed or dashed suffixes that don't change
    the recording: "(Remastered 2011)", "- 2003 Remaster", "[Deluxe Edition]",
    "(feat. X)", "(Mono)", "(Album Version)". Live/acoustic/demo/remix suffixes are kept,
    since those are different recordings."""

    return _plain(_without_same_recording(title))


def _without_same_recording(title: str) -> str:
    def drop_if_same(m: re.Match[str]) -> str:
        return "" if _SAME_RECORDING.search(m.group(1)) else m.group(0)

    title = _BRACKETED.sub(drop_if_same, title)
    return _DASHED.sub(drop_if_same, title)


def part_title(title: str) -> Optional[str]:
    """The part name of a "<suite> - <part>" title, e.g. "Retrospect" for
    "Of Matter - Retrospect", which is how tab sites tend to list it.

    Takes the text after the last spaced dash (-, – or —) once same-recording suffixes
    such as "- 2013 Remaster" or "(Remastered)" are removed. Returns None when there is
    no such dash, or when that text names a version rather than a part (live, acoustic,
    demo, remix, mix, edit, version, remaster, mono, stereo, instrumental, unplugged,
    cover, karaoke)."""
    m = _DASHED.search(_without_same_recording(title))
    if m is None:
        return None
    part = m.group(1).strip()
    if not _plain(part) or _VERSION.search(part):
        return None
    return part


def normalise_artist(artist: str) -> str:
    """Lowercase, drop punctuation, drop a leading "the ", and treat "&" as "and"."""
    plain = _plain(artist)
    return plain[4:] if plain.startswith("the ") else plain


def is_exact(artist: str, title: str, other_artist: str, other_title: str) -> bool:
    """True when both normalised artist and normalised title are equal."""
    return normalise_artist(artist) == normalise_artist(other_artist) and normalise_title(
        title
    ) == normalise_title(other_title)


def is_similar(artist: str, title: str, other_artist: str, other_title: str) -> bool:
    """True when the artists match and one normalised title contains the other
    (e.g. "Schism" vs "Schism Live"). Used to keep fuzzy candidates for review."""
    if normalise_artist(artist) != normalise_artist(other_artist):
        return False
    a, b = normalise_title(title), normalise_title(other_title)
    return bool(a and b) and (a in b or b in a)
