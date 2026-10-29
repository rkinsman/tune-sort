"""Shared fakes and builders for the tune-sort tests."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import pytest

from tune_sort.music import MusicError, Track
from tune_sort.sources import FetchError, Match, SourceError
from tune_sort.tuning import Tuning

FIXTURES = Path(__file__).parent / "fixtures"

DASH = "–"
ARROW = "→"

_PC = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6,
    "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}  # fmt: skip


def fixture_text(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


def T(text: str, instrument: str = "bass") -> Tuning:
    """Build a Tuning from space-separated note names (lowest first).

    Deliberately independent of tune_sort.tuning's parsers.
    """
    pcs = tuple(_PC[n.upper()] for n in text.split())
    if instrument == "bass":
        return Tuning(pcs)
    return Tuning(pcs, instrument)  # type: ignore[arg-type]


# ---------------------------------------------------------------- UG builders


def store_page(data: Dict[str, Any]) -> str:
    """Build a UG-style page whose js-store holds {"store": {"page": {"data": data}}}."""
    payload = json.dumps({"store": {"page": {"data": data}}})
    return (
        '<!DOCTYPE html><html><body><div class="js-store" data-content="'
        + html.escape(payload, quote=True)
        + '"></div></body></html>'
    )


def ug_result(
    id: Optional[int],
    type: Optional[str],
    rating: float = 4.0,
    votes: int = 10,
    artist: str = "Tool",
    title: str = "Schism",
    slug: str = "x",
) -> Dict[str, Any]:
    return {
        "id": id,
        "song_name": title,
        "artist_name": artist,
        "type": type,
        "marketing_type": None if type else "official",
        "rating": rating,
        "votes": votes,
        "tab_url": "https://tabs.ultimate-guitar.com/tab/%s/%s-%s-%s"
        % (artist.lower().replace(" ", "-"), title.lower().replace(" ", "-"), slug, id),
        "tab_access_type": "public" if type else None,
    }


def ug_search_page(results: List[Dict[str, Any]]) -> str:
    return store_page({"search_query": "q", "results": results})


def ug_tab_page(
    tuning_value: Optional[str] = "E A D G",
    instruments: str = "bass",
    instruments_count: int = 1,
    with_tuning: bool = True,
) -> str:
    meta: Dict[str, Any] = {"instruments": instruments, "instrumentsCount": instruments_count}
    if with_tuning:
        meta["tuning"] = {"name": "n", "value": tuning_value, "index": 0}
    return store_page({"tab_view": {"meta": meta}})


class FakeFetch:
    """fetch(url) -> str. Search URLs (by prefix) get `search_response`; others come from `pages`.

    Unknown URLs raise FetchError, except that when `extra_pro_page` is given, unknown URLs
    containing "guitar-pro" are served that page. A response that is an Exception instance is
    raised.
    """

    def __init__(
        self,
        pages: Optional[Dict[str, Any]] = None,
        search_prefix: Optional[str] = None,
        search_response: Any = None,
        extra_pro_page: Optional[str] = None,
    ) -> None:
        self.pages = dict(pages or {})
        self.search_prefix = search_prefix
        self.search_response = search_response
        self.extra_pro_page = extra_pro_page
        self.calls: List[str] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        if self.search_prefix is not None and url.startswith(self.search_prefix):
            if isinstance(self.search_response, Exception):
                raise self.search_response
            return str(self.search_response)
        if url in self.pages:
            value = self.pages[url]
            if isinstance(value, Exception):
                raise value
            return str(value)
        if self.extra_pro_page is not None and "guitar-pro" in url:
            return self.extra_pro_page
        raise FetchError("unknown url: " + url)

    def tab_calls(self) -> List[str]:
        return [
            c for c in self.calls if not (self.search_prefix and c.startswith(self.search_prefix))
        ]


# ------------------------------------------------------------------- Music fake


class FakeMusic:
    """In-memory implementation of the Music protocol that records mutating calls.

    `fail_add` maps a persistent id to the message of the MusicError add_track raises for it.
    """

    def __init__(
        self,
        playlists: Optional[Dict[str, List[Track]]] = None,
        fail_add: Optional[Dict[str, str]] = None,
    ) -> None:
        self.fail_add: Dict[str, str] = dict(fail_add or {})
        self.playlists: Dict[str, List[Track]] = {k: list(v) for k, v in (playlists or {}).items()}
        self.library: Dict[str, Track] = {}
        for tracks in self.playlists.values():
            for t in tracks:
                self.library[t.persistent_id] = t
        self.ensure_calls: List[str] = []
        self.add_calls: List[Tuple[str, str]] = []

    def list_playlists(self) -> List[str]:
        return list(self.playlists)

    def get_tracks(self, playlist: str) -> List[Track]:
        if playlist not in self.playlists:
            raise MusicError("no such playlist: " + playlist)
        return list(self.playlists[playlist])

    def ensure_playlist(self, name: str) -> bool:
        self.ensure_calls.append(name)
        if name in self.playlists:
            return False
        self.playlists[name] = []
        return True

    def add_track(self, playlist: str, persistent_id: str) -> bool:
        self.add_calls.append((playlist, persistent_id))
        if persistent_id in self.fail_add:
            raise MusicError(self.fail_add[persistent_id])
        if playlist not in self.playlists:
            raise MusicError("no such playlist: " + playlist)
        if any(t.persistent_id == persistent_id for t in self.playlists[playlist]):
            return False
        self.playlists[playlist].append(self.library[persistent_id])
        return True


def make_track(pid: str, artist: str, name: str, album: str = "Album") -> Track:
    return Track(persistent_id=pid, name=name, artist=artist, album=album)


# ----------------------------------------------------------------- Source fake


def make_match(
    tuning_text: str,
    source: str = "ug-bass",
    exact: bool = True,
    artist: str = "Tool",
    title: str = "Schism",
    instrument: str = "bass",
) -> Match:
    return Match(
        tuning=T(tuning_text, instrument),
        source=source,
        url="https://example.test/" + source,
        matched_artist=artist,
        matched_title=title,
        exact=exact,
    )


class FakeSource:
    """Source with a name and scripted answers keyed by (artist, title).

    An answer (or the default) that is an Exception instance is raised by `lookup`.
    """

    def __init__(
        self,
        name: str,
        answers: Optional[Dict[Tuple[str, str], Any]] = None,
        default: Any = None,
    ) -> None:
        self.name = name
        self.answers = dict(answers or {})
        self.default = default
        self.calls: List[Tuple[str, str]] = []

    def lookup(self, artist: str, title: str) -> Optional[Match]:
        self.calls.append((artist, title))
        value = self.answers.get((artist, title), self.default)
        if isinstance(value, Exception):
            raise value
        return cast("Optional[Match]", value)


def failing_source(name: str) -> FakeSource:
    """A FakeSource whose lookup always raises SourceError."""
    return FakeSource(name, default=SourceError("%s is down" % name))


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "c.db"


@pytest.fixture
def cache(tmp_path: Path):  # type: ignore[no-untyped-def]
    from tune_sort.cache import Cache

    c = Cache(tmp_path / "cache" / "c.db")
    yield c
    c.close()


@pytest.fixture
def guitar_cache(tmp_path: Path):  # type: ignore[no-untyped-def]
    from tune_sort.cache import Cache

    c = Cache(tmp_path / "gcache" / "c.db", "guitar")
    yield c
    c.close()
