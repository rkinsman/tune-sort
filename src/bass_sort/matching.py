"""Deciding whether a tab site's song is the same song as an Apple Music track."""

from __future__ import annotations

import re
import unicodedata

# Bracketed or dashed suffixes that name the same recording.
_SAME_RECORDING = re.compile(
    r"remaster|deluxe|feat\.?|ft\.|featuring|mono|stereo|album version|single version"
    r"|radio edit|bonus track|expanded|anniversary|edition",
    re.IGNORECASE,
)
_BRACKETED = re.compile(r"\s*[(\[]([^)\]]*)[)\]]")
_DASHED = re.compile(r"\s+-\s+(.*)$")


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

    def drop_if_same(m: re.Match[str]) -> str:
        return "" if _SAME_RECORDING.search(m.group(1)) else m.group(0)

    title = _BRACKETED.sub(drop_if_same, title)
    title = _DASHED.sub(drop_if_same, title)
    return _plain(title)


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
