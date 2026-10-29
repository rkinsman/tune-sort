"""The helper's JSON-lines protocol loop (`tune-sort serve`), version 1.

Reads one UTF-8 JSON object per line from stdin: `{"id": <int>, "cmd": <name>, "args": {...}}`.
Each request gets exactly one reply line on stdout, carrying its id:
`{"id", "result": ...}` or `{"id", "error": {"kind", "message"}}`. A line that is not a JSON
object with an integer `id` and a string `cmd` gets `bad_request` with `"id": null` (or the
id, if one could be read). Replies are written with `ensure_ascii=False` and flushed.

Commands here: hello, playlists, tracks, config, set_order, review_list, describe, set,
entries, delete (shapes in the spec's "Protocol (version 1)"). `instrument` is "bass" or
"guitar". Error kinds: bad_request (unknown command, missing or wrong-typed args),
music (MusicError), config (ConfigError, same text as the CLI), bad_tuning (same text as
the CLI), internal (any other exception; traceback to stderr, the loop keeps running).
`serve` returns at end of input.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

from tune_sort.cache import Cache, Entry
from tune_sort.cli import SourcesFactory, bad_tuning_message
from tune_sort.config import SOURCE_NAMES, ConfigError, load_order, save_order
from tune_sort.music import Music, MusicError
from tune_sort.sorter import track_states
from tune_sort.tuning import INSTRUMENTS, Instrument, Tuning, TuningParseError, parse_name
from tune_sort.wire import cached_song_json, match_json, track_state_json, tuning_json

PROTOCOL_VERSION = 1

# Opens the cache for an instrument.
CacheFactory = Callable[[Instrument], Cache]


class BadRequest(Exception):
    """The request's command or arguments are invalid."""


class BadTuning(Exception):
    """A tuning that can't be parsed; the message matches the CLI's."""


def _parse(text: str, instrument: Instrument) -> Tuning:
    try:
        return parse_name(text, instrument)
    except TuningParseError as e:
        raise BadTuning(bad_tuning_message(text, e)) from e


class _Session:
    """The helper's shared state: Music (created on first use) and one open cache per
    instrument."""

    def __init__(
        self,
        music: Callable[[], Music],
        sources: SourcesFactory,
        cache: CacheFactory,
        config_path: Path,
    ) -> None:
        self._music_factory = music
        self.sources = sources
        self._cache_factory = cache
        self.config_path = config_path
        self._music: Music | None = None
        self._caches: dict[Instrument, Cache] = {}

    def music(self) -> Music:
        if self._music is None:
            self._music = self._music_factory()
        return self._music

    def cache(self, instrument: Instrument) -> Cache:
        if instrument not in self._caches:
            self._caches[instrument] = self._cache_factory(instrument)
        return self._caches[instrument]

    def close(self) -> None:
        for cache in self._caches.values():
            cache.close()


Handler = Callable[[_Session, dict[str, Any]], Any]


def _str(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str):
        raise BadRequest(f"{name} must be a string")
    return value


def _instrument(args: dict[str, Any]) -> Instrument:
    value = args.get("instrument")
    for instrument in INSTRUMENTS:
        if value == instrument:
            return instrument
    raise BadRequest(f"instrument must be one of: {', '.join(INSTRUMENTS)}")


def _hello(session: _Session, args: dict[str, Any]) -> Any:
    return {"protocol": PROTOCOL_VERSION, "instruments": list(INSTRUMENTS)}


def _playlists(session: _Session, args: dict[str, Any]) -> Any:
    return session.music().list_playlists()


def _tracks(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    playlist = _str(args, "playlist")
    states = track_states(session.music(), playlist, session.cache(instrument))
    return [track_state_json(s) for s in states]


def _config(session: _Session, args: dict[str, Any]) -> Any:
    return {
        "path": str(session.config_path),
        "exists": session.config_path.exists(),
        "order": {i: load_order(i, session.config_path) for i in INSTRUMENTS},
        "sources": {i: list(SOURCE_NAMES[i]) for i in INSTRUMENTS},
    }


def _set_order(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    if "order" not in args:
        raise BadRequest("order is required (a list, or null for the default)")
    order = args["order"]
    if order is not None and not (
        isinstance(order, list) and all(isinstance(n, str) for n in order)
    ):
        raise BadRequest("order must be a list of strings or null")
    return save_order(instrument, order, session.config_path)


def _review_list(session: _Session, args: dict[str, Any]) -> Any:
    items = session.cache(_instrument(args)).review_items()
    return [
        {
            "artist": i.artist,
            "title": i.title,
            "candidates": [match_json(m) for m in i.candidates],
        }
        for i in items
    ]


def _describe(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    text = _str(args, "tuning")
    return {"tuning": tuning_json(_parse(text, instrument))}


def _set(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    artist, title, text = _str(args, "artist"), _str(args, "title"), _str(args, "tuning")
    entry = Entry(_parse(text, instrument), "manual", confirmed=True)
    cache = session.cache(instrument)
    cache.put(artist, title, entry)
    stored = [s for s in cache.entries() if (s.artist, s.title) == (artist, title)]
    return (
        cached_song_json(stored[0])
        if stored
        else {
            "artist": artist,
            "title": title,
            "tuning": tuning_json(entry.tuning),
            "source": entry.source,
            "confirmed": entry.confirmed,
        }
    )


def _entries(session: _Session, args: dict[str, Any]) -> Any:
    return [cached_song_json(s) for s in session.cache(_instrument(args)).entries()]


def _delete(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    session.cache(instrument).delete(_str(args, "artist"), _str(args, "title"))
    return {}


# Command name -> handler. Handlers raise BadRequest for bad arguments.
HANDLERS: dict[str, Handler] = {
    "hello": _hello,
    "playlists": _playlists,
    "tracks": _tracks,
    "config": _config,
    "set_order": _set_order,
    "review_list": _review_list,
    "describe": _describe,
    "set": _set,
    "entries": _entries,
    "delete": _delete,
}


def _write(stdout: TextIO, obj: dict[str, Any]) -> None:
    stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stdout.flush()


def _error(id: int | None, kind: str, message: str) -> dict[str, Any]:
    return {"id": id, "error": {"kind": kind, "message": message}}


def _handle(session: _Session, line: str) -> dict[str, Any]:
    id: int | None = None
    try:
        try:
            request = json.loads(line)
        except ValueError as e:
            raise BadRequest(f"not valid JSON: {e}") from e
        if not isinstance(request, dict):
            raise BadRequest("request must be a JSON object")
        raw_id = request.get("id")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool):
            id = raw_id
        else:
            raise BadRequest("id must be an integer")
        cmd = request.get("cmd")
        if not isinstance(cmd, str):
            raise BadRequest("cmd must be a string")
        handler = HANDLERS.get(cmd)
        if handler is None:
            raise BadRequest(f"unknown command: {cmd}")
        args = request.get("args", {})
        if not isinstance(args, dict):
            raise BadRequest("args must be an object")
        return {"id": id, "result": handler(session, args)}
    except BadRequest as e:
        return _error(id, "bad_request", str(e))
    except MusicError as e:
        return _error(id, "music", str(e))
    except ConfigError as e:
        return _error(id, "config", str(e))
    except BadTuning as e:
        return _error(id, "bad_tuning", str(e))
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return _error(id, "internal", f"{type(e).__name__}: {e}")


def serve(
    stdin: TextIO,
    stdout: TextIO,
    music: Callable[[], Music],
    sources: SourcesFactory,
    cache: CacheFactory,
    config_path: Path,
) -> None:
    """Answer requests from `stdin` on `stdout` until end of input (see the module
    docstring). `music` is called once, on first use; caches are opened once per
    instrument, on first use."""
    session = _Session(music, sources, cache, config_path)
    try:
        for line in stdin:
            if line.strip():
                _write(stdout, _handle(session, line))
    finally:
        session.close()
