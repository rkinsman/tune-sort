"""The helper's JSON-lines protocol loop (`tune-sort serve`), version 1.

Reads one UTF-8 JSON object per line from stdin: `{"id": <int>, "cmd": <name>, "args": {...}}`.
Each request gets exactly one reply line on stdout, carrying its id:
`{"id", "result": ...}` or `{"id", "error": {"kind", "message"}}`. A line that is not a JSON
object with an integer `id` and a string `cmd` gets `bad_request` with `"id": null` (or the
id, if one could be read). Replies are written with `ensure_ascii=False` and flushed.

Commands here: hello, playlists, tracks, config, set_order, sort, cancel, review_list,
describe, set, entries, delete (shapes in the spec's "Protocol (version 1)").
`instrument` is "bass" or "guitar". Error kinds: bad_request (unknown command, missing or
wrong-typed args), music (MusicError), config (ConfigError, same text as the CLI),
bad_tuning (same text as the CLI), internal (any other exception; traceback to stderr, the
loop keeps running), busy (a request other than cancel while a sort is running).

Threads: a reader thread reads stdin. It answers unparseable lines, `cancel` and `busy`
itself and queues every other request for the calling ("main") thread, which runs them
one at a time; Music, the caches and the sources are only used there. A sort counts as
running from when its line is read until its final reply is written; meanwhile the reader
keeps reading. For any other request the reader waits for the reply before reading on,
so pipelined requests are answered in order and never get `busy`. All output goes through
one lock, one whole line per write.

A sort writes `start` and `done` events (`{"id", "event", "data"}`) before its result.
`cancel` (args `{"id"}`) stops the running sort with that id before its next track and
replies `{}`; the sort's report then has `cancelled: true`. End of input cancels a
running sort the same way; `serve` returns once the running request has replied.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, TextIO

from tune_sort.cache import Cache, Entry
from tune_sort.cli import SourcesFactory, bad_tuning_message
from tune_sort.config import SOURCE_NAMES, ConfigError, load_order, parse_order, save_order
from tune_sort.music import Music, MusicError, Track
from tune_sort.resolver import Resolution
from tune_sort.sorter import Status, sort_playlist, track_states
from tune_sort.sources import Source
from tune_sort.tuning import INSTRUMENTS, Instrument, Tuning, TuningParseError, parse_name
from tune_sort.wire import (
    cached_song_json,
    match_json,
    report_json,
    track_state_json,
    tuning_json,
)

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
        self._sources: dict[tuple[Instrument, tuple[str, ...]], list[Source]] = {}
        # A writer for the running request's events (set by the main thread) and the
        # flag that `cancel` and end of input set.
        self.emit: Callable[[str, dict[str, Any]], None] = lambda kind, data: None
        self.stop = threading.Event()

    def music(self) -> Music:
        if self._music is None:
            self._music = self._music_factory()
        return self._music

    def cache(self, instrument: Instrument) -> Cache:
        if instrument not in self._caches:
            self._caches[instrument] = self._cache_factory(instrument)
        return self._caches[instrument]

    def sources_for(self, instrument: Instrument, names: list[str]) -> list[Source]:
        """The sources for these names, made once per instrument and order."""
        key = (instrument, tuple(names))
        if key not in self._sources:
            self._sources[key] = self.sources(instrument, names)
        return self._sources[key]

    def close(self) -> None:
        for cache in self._caches.values():
            cache.close()


Handler = Callable[[_Session, dict[str, Any]], Any]


def _str(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str):
        raise BadRequest(f"{name} must be a string")
    return value


def _flag(args: dict[str, Any], name: str) -> bool:
    value = args.get(name, False)
    if not isinstance(value, bool):
        raise BadRequest(f"{name} must be true or false")
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


SOURCE_CHOICES = ("both", "ug", "songsterr")


def _sort_names(session: _Session, instrument: Instrument, args: dict[str, Any]) -> list[str]:
    """The source names for a sort: `order` (or the saved order), filtered by `source`.
    Same rules and messages as the CLI's --order and --source."""
    source = args.get("source", "both")
    if source is None:
        source = "both"
    if source not in SOURCE_CHOICES:
        raise BadRequest(f"source must be one of: {', '.join(SOURCE_CHOICES)}")
    order = args.get("order")
    if order is None:
        names = load_order(instrument, session.config_path)
    else:
        if not (isinstance(order, list) and all(isinstance(n, str) for n in order)):
            raise BadRequest("order must be a list of strings")
        if any("," in n for n in order):
            raise ConfigError("order: source names can't contain commas")
        names = parse_order(",".join(order), instrument) if order else []
        if not names:
            raise ConfigError("order: must name at least one source")
    if source == "ug":
        names = [n for n in names if n.startswith("ug-")]
    elif source == "songsterr":
        names = [n for n in names if n == "songsterr"]
    if not names:
        raise ConfigError(f"no sources left after --source {source}")
    return names


def _done_json(
    track: Track,
    resolution: Resolution,
    status: Status,
    playlist: Optional[str],
    error: Optional[str],
) -> dict[str, Any]:
    data: dict[str, Any] = {"artist": track.artist, "title": track.name, "status": status}
    if resolution.tuning is not None:
        data["tuning"] = tuning_json(resolution.tuning)
    if resolution.source is not None:
        data["source"] = resolution.source
    if playlist is not None:
        data["playlist"] = playlist
    if resolution.failed:
        data["failed"] = list(resolution.failed)
    if error is not None:
        data["error"] = error
    return data


def _sort(session: _Session, args: dict[str, Any]) -> Any:
    instrument = _instrument(args)
    playlist = _str(args, "playlist")
    dry_run, recheck = _flag(args, "dry_run"), _flag(args, "recheck")
    names = _sort_names(session, instrument, args)
    music = session.music()
    sources = session.sources_for(instrument, names)
    cache = session.cache(instrument)

    def start(i: int, total: int, track: Track) -> None:
        session.emit("start", {"i": i, "total": total, "artist": track.artist, "title": track.name})

    def done(
        track: Track,
        resolution: Resolution,
        status: Status,
        target: Optional[str],
        error: Optional[str],
    ) -> None:
        session.emit("done", _done_json(track, resolution, status, target, error))

    report = sort_playlist(
        music,
        playlist,
        sources,
        cache,
        dry_run,
        on_progress=start,
        recheck=recheck,
        should_stop=session.stop.is_set,
        on_done=done,
    )
    return report_json(report)


def _cancel(session: _Session, args: dict[str, Any]) -> Any:
    # Answered by the reader thread (see _Reader); never queued.
    raise BadRequest("cancel is handled by the reader")


# Command name -> handler. Handlers raise BadRequest for bad arguments.
HANDLERS: dict[str, Handler] = {
    "hello": _hello,
    "playlists": _playlists,
    "tracks": _tracks,
    "config": _config,
    "set_order": _set_order,
    "sort": _sort,
    "cancel": _cancel,
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


@dataclass
class _Request:
    id: int
    cmd: str
    args: dict[str, Any]
    finished: threading.Event = field(default_factory=threading.Event)


def _parse_request(line: str) -> _Request:
    """The request on `line`. Raises _Invalid (carrying the id, if one could be read)."""
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
        args = request.get("args", {})
        if not isinstance(args, dict):
            raise BadRequest("args must be an object")
        return _Request(id, cmd, args)
    except BadRequest as e:
        raise _Invalid(id, str(e)) from e


class _Invalid(Exception):
    def __init__(self, id: int | None, message: str) -> None:
        super().__init__(message)
        self.id = id


def _run(session: _Session, request: _Request) -> dict[str, Any]:
    """Run one request on the main thread and return its final reply."""
    id = request.id
    try:
        handler = HANDLERS.get(request.cmd)
        if handler is None:
            raise BadRequest(f"unknown command: {request.cmd}")
        return {"id": id, "result": handler(session, request.args)}
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


_END: Literal["end"] = "end"


class _Server:
    def __init__(self, stdin: TextIO, stdout: TextIO, session: _Session) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.session = session
        self.queue: queue.Queue[_Request | Literal["end"]] = queue.Queue()
        # Guards all output and `running` (the id of the running sort), so a reply and
        # the state it implies change together.
        self.lock = threading.Lock()
        self.running: int | None = None

    def write(self, obj: dict[str, Any]) -> None:
        with self.lock:
            _write(self.stdout, obj)

    # ---- reader thread: stdin, cancel and busy; never touches Music or the caches.

    def read(self) -> None:
        try:
            for line in iter(self.stdin.readline, ""):
                if line.strip():
                    self._accept(line)
        except Exception:
            traceback.print_exc(file=sys.stderr)
        finally:
            with self.lock:
                if self.running is not None:
                    self.session.stop.set()
            self.queue.put(_END)

    def _accept(self, line: str) -> None:
        try:
            request = _parse_request(line)
        except _Invalid as e:
            self.write(_error(e.id, "bad_request", str(e)))
            return
        if request.cmd == "cancel":
            self._cancel(request)
            return
        with self.lock:
            if self.running is not None:
                _write(
                    self.stdout,
                    _error(request.id, "busy", f"request {self.running} is still running"),
                )
                return
            if request.cmd == "sort":
                self.running = request.id
                self.session.stop.clear()
        self.queue.put(request)
        if request.cmd != "sort":
            request.finished.wait()

    def _cancel(self, request: _Request) -> None:
        target = request.args.get("id")
        with self.lock:
            if not isinstance(target, int) or isinstance(target, bool):
                reply = _error(request.id, "bad_request", "id must be an integer")
            elif target != self.running:
                reply = _error(request.id, "bad_request", f"no request {target} is running")
            else:
                self.session.stop.set()
                reply = {"id": request.id, "result": {}}
            _write(self.stdout, reply)

    # ---- main thread: runs requests one at a time.

    def _emitter(self, id: int) -> Callable[[str, dict[str, Any]], None]:
        def emit(kind: str, data: dict[str, Any]) -> None:
            self.write({"id": id, "event": kind, "data": data})

        return emit

    def run(self) -> None:
        while True:
            request = self.queue.get()
            if request == _END:
                return
            assert isinstance(request, _Request)
            id = request.id
            self.session.emit = self._emitter(id)
            reply = _run(self.session, request)
            with self.lock:
                _write(self.stdout, reply)
                if self.running == id:
                    self.running = None
            request.finished.set()


def serve(
    stdin: TextIO,
    stdout: TextIO,
    music: Callable[[], Music],
    sources: SourcesFactory,
    cache: CacheFactory,
    config_path: Path,
) -> None:
    """Answer requests from `stdin` on `stdout` until end of input (see the module
    docstring). Requests run on the calling thread. `music` is called once, on first use;
    caches are opened once per instrument, and sources once per instrument and order, on
    first use."""
    session = _Session(music, sources, cache, config_path)
    server = _Server(stdin, stdout, session)
    reader = threading.Thread(target=server.read, name="tune-sort-serve-reader", daemon=True)
    reader.start()
    try:
        server.run()
    finally:
        session.close()
    reader.join()
