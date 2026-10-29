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

from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from tune_sort.cache import Cache
from tune_sort.cli import SourcesFactory
from tune_sort.music import Music
from tune_sort.tuning import Instrument

PROTOCOL_VERSION = 1

# Opens the cache for an instrument.
CacheFactory = Callable[[Instrument], Cache]


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
    raise NotImplementedError
