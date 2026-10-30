# TuneSort Mac app: design

Date: 2026-10-29
Status: draft for review

## Goal

A native macOS app that does everything the `tune-sort` CLI does: sort a Music playlist
into tuning playlists (preview and real), work through the review queue, browse and fix
cached tunings, and edit the source order. It is for one user on this Mac, built from
this repo. No signing, notarization, bundled Python or distribution.

Success means the CLI is no longer needed for day-to-day use, and the app's results
match the CLI's for the same playlist, cache and config.

## Architecture

Two parts in one repo:

- **`tune-sort serve`** (new, `src/tune_sort/serve.py`): a long-lived helper that reads
  JSON requests on stdin and writes JSON replies on stdout. It is a thin adapter over the
  existing core (`sorter`, `resolver`, `cache`, `music`, `config`, `tuning`) and holds no
  tuning logic of its own.
- **TuneSort.app** (new, `mac/`): a SwiftUI front end. All logic stays in Python.

### Helper lifecycle

- At launch the app runs `<repo>/.venv/bin/tune-sort serve`. The repo path is a setting,
  defaulting to `~/code/tune-sort`.
- One helper process for the app's lifetime: one cache connection and one HTTP client,
  so in-memory memoising carries across requests.
- One request runs at a time. A reader thread reads stdin; the main thread runs requests.
  `cancel` is handled by the reader thread; any other request arriving while one is
  running gets a `busy` error.
- On quit the app closes the helper's stdin; the helper exits at end of input.
- `serve` accepts `--cache PATH` and `--config PATH` like the other commands.
- stdout carries protocol messages only. Diagnostics go to stderr, which the app shows
  in a log view.

### Apple Events

osascript runs as a descendant of the app, so macOS asks once whether TuneSort may
control Music. The app is not sandboxed; its Info.plist carries
`NSAppleEventsUsageDescription`.

## Protocol (version 1)

One UTF-8 JSON object per line.

- Request: `{"id": <int>, "cmd": "<name>", "args": {...}}`
- Replies carry the request's `id` and are one of:
  - `{"id": n, "event": "<kind>", "data": {...}}`: zero or more (sort only)
  - `{"id": n, "result": ...}`: exactly one on success
  - `{"id": n, "error": {"kind": "<kind>", "message": "<text>"}}`: exactly one on failure
- A line that is not a JSON object with an integer `id` and a string `cmd` gets
  `bad_request` with `"id": null` (or the `id`, if one could be read).

### Commands

`instrument` is `"bass"` or `"guitar"` everywhere.

| cmd | args | result |
|---|---|---|
| `hello` | none | `{"protocol": 1, "instruments": ["bass", "guitar"]}` |
| `playlists` | none | `[name, ...]`, all Music playlists |
| `tracks` | `instrument, playlist` | the playlist's tracks, each with its cache state (below). No network calls |
| `config` | none | `{"path", "exists", "order": {"bass": [...], "guitar": [...]}, "sources": {"bass": [...], "guitar": [...]}}` (`sources` lists every allowed name) |
| `set_order` | `instrument, order` (a list, or `null` for the default) | the new effective order |
| `sort` | `instrument, playlist, dry_run, order?, source?, recheck` | progress events, then the report (below) |
| `cancel` | `id` (of the running sort) | `{}`; `bad_request` if no request with that id is running |
| `review_list` | `instrument` | `[{"artist", "title", "candidates": [match, ...]}]` |
| `describe` | `instrument, tuning` | `{"tuning": tuning}`, or a `bad_tuning` error |
| `set` | `instrument, artist, title, tuning` | the stored entry. Same effect as `tune-sort <instrument> set` |
| `entries` | `instrument` | every cached entry for the instrument: `[{"artist", "title", "tuning", "source", "confirmed"}]` |
| `delete` | `instrument, artist, title` | `{}`. Forgets the cached tuning and any review-queue entry, so the next sort looks the song up again. Deleting a song that isn't cached is not an error |

`order` and `source` in `sort` mean the same as `--order` (a list here) and `--source`
(`both`, `ug` or `songsterr`). Without `order`, the saved order is used.

### Data shapes

- **track**: `{"artist", "title", "persistent_id"}`
- **tuning**: `{"name", "playlist_name", "notes"}`, e.g. `{"name": "Drop D",
  "playlist_name": "Bass – Drop D", "notes": "D A D G"}`
- **match**: `{"tuning": tuning, "source", "url", "matched_artist", "matched_title",
  "exact"}`
- `notes` in a tuning is the open-string note names, lowest string first, separated by spaces
- **tracks item**: a track plus `"state"`: `"cached"` (with `tuning`, `source`,
  `confirmed`), `"review"` (with `candidates`) or `"unknown"`
- **report**: `{"cancelled", "created_playlists", "added": {playlist: [track]},
  "already_present": {playlist: [track]}, "review": [track], "lookup_failed": [track],
  "add_errors": [{"track", "playlist", "error"}]}`. In a dry run `added` means "would add".

### Sort progress events

- `start`: `{"i", "total", "artist", "title"}` just before a track is resolved.
- `done`: `{"artist", "title", "status", "tuning"?, "source"?, "playlist"?, "failed"?,
  "error"?}` after a track is handled. `status` is one of `added` (would add, in a dry
  run), `already_present`, `review`, `lookup_failed` or `add_error`.

### Error kinds

| kind | when |
|---|---|
| `bad_request` | unknown command, missing or wrong-typed args, unparseable line |
| `busy` | a request other than `cancel` arrives while one is running |
| `music` | a `MusicError` (Music not running, permission denied, playlist missing) |
| `config` | invalid config file or order; same message text as the CLI |
| `bad_tuning` | a tuning that can't be parsed; same message text as the CLI |
| `internal` | any other exception. The traceback goes to stderr; the helper keeps running |

## Changes to the core

All are public interfaces and get tests like the rest.

- `sort_playlist` gains two optional parameters:
  - `should_stop: Callable[[], bool]`, checked before each track. When true, the sort
    stops and returns the report so far with `Report.cancelled = True` (a new field,
    default `False`). Music changes already made stay made; the report lists them.
  - `on_done(track, resolution, status, playlist, error)`, called after each track is
    handled, with `status` as in the `done` event.
- The `tunings` table stores only normalised song keys today, so it gains nullable `artist`
  and `title` columns, added with `ALTER TABLE` when missing. `put` fills them with the
  names as given.
- `Cache.entries() -> list[CachedSong]`: every cached entry for the cache's instrument (a
  `Cache` is opened per instrument), sorted by artist then title, ignoring case. Each item
  has `artist`, `title` and `entry`. Rows written before the columns existed use the
  normalised artist and title from the key.
- `Cache.delete(artist, title)`, removing the entry and any queued review item.
- `config.save_order(instrument, order | None, path=CONFIG_PATH)`:
  - Validates `order` by the same rules as `load_order` and raises `ConfigError` if invalid.
  - `None` removes that instrument's order (back to the default).
  - Creates the parent directory if needed and writes atomically (temp file, then rename).
  - The file only ever holds `[bass]` and `[guitar]` tables with an `order` key, written
    by a small writer for that shape. If the existing file is invalid or contains
    anything else, it raises `ConfigError` and leaves the file alone. Comments are not kept.
- The `tracks` lookup (playlist tracks with cache state) lives in the core, not in
  `serve.py`, so it is tested without the protocol.

## The app

### Window

The layout is playlist-centred: a sidebar, a song table, and a side panel for the
selected song.

**Toolbar**
- **Bass / Guitar switch.** It applies to everything in the window.
- **Sources ▾.** A per-run order override, defaulting to the saved order.
- **Preview** (a dry run) and **Sort**. While a run is going, both are replaced by
  "Sorting i / n" with a progress bar, and a **Stop** button that sends `cancel`.
- **Sort confirmation.** Sort always asks before changing Music. If a preview of the same
  playlist, instrument and sources was the last run, the dialog uses its figures, e.g.
  "Add 14 songs to 3 playlists, creating 1?". Otherwise it asks "Sort 'Drop D' into
  tuning playlists?".

**Sidebar**
- **Needs review**, with a count badge: every queued song for the instrument (`review_list`).
- **All songs**: the instrument's whole cache (`entries`), with a search field.
- **Playlists**: Music playlists from `playlists`, except tuning playlists.
- **Tuning playlists**: playlists named like the instrument's tuning playlists: `Bass – …`
  or `Bass N-String – …` (`Guitar – …` or `Guitar N-String – …` for guitar). Shown dimmed;
  they can be browsed but not sorted.

**Song table**
- Columns: Song, Tuning, Source.
- Selecting a playlist loads `tracks`, so cached tunings show at once. Uncached songs
  read "not looked up".
- During a run, rows update from `start` and `done` events.
- A footer summarises the last run (added or would add, needs review, failed).

**Side panel (selected song)**
- **Needs review:** the candidate matches as buttons (click one to use its tuning) and a
  tuning field. The field is checked as you type with `describe`, showing the target
  playlist or the parse error inline. **Save** sends `set`.
- **Cached:** the tuning, its notes, source and whether it is confirmed, plus a field to
  **Change** it (`set`) and a **Clear** button (`delete`).
- **Lookup failed:** which sources failed, and a note that the next sort retries.
- **Not looked up:** a note that sorting looks it up.

Changing a sorted song's tuning updates the cache only. The song stays in its old tuning
playlist, and the next sort adds it to the new one.

**Settings window (⌘,)**
- **Source order per instrument:** a list you can drag to reorder, an on/off toggle per
  source (at least one stays on), and **Reset to default**. Changes are saved with
  `set_order`; a `config` error is shown inline.
- **Repo path:** where the app finds the helper.
- **Log:** the helper's stderr.

### Error handling

| Situation | What the app does |
|---|---|
| Helper binary missing | Setup screen: the path tried, a "run `uv sync` in the repo" hint, and the repo path field |
| `hello` protocol mismatch | "Helper speaks protocol N, the app expects M. Pull and rebuild." Nothing else runs |
| Helper exits or crashes | Banner with the last stderr lines and **Restart**. The running request fails, and rows showing "looking up…" go back to their previous state |
| `music` error | Banner. For a denied Automation permission, a button opens System Settings → Privacy & Security → Automation |
| `config` error | Banner linking to Settings. Sorting is blocked until it's fixed |
| `bad_tuning` | Inline under the tuning field |
| A source fails for a song | Row shows "failed, will retry" (not an error) |
| Non-JSON line from the helper | Logged and ignored |

## Repo layout and build

```
src/tune_sort/serve.py          protocol adapter (+ `serve` command in cli.py)
mac/Package.swift               Swift package
mac/Sources/TuneSortCore/       helper client, models, view models
mac/Sources/TuneSort/           SwiftUI views and app entry point
mac/Tests/TuneSortCoreTests/    tests for TuneSortCore
```

- Xcode is required, for the SDK and XCTest. The package builds and tests from the shell
  (`swift build`, `swift test`), and Xcode opens `Package.swift` directly.
- A build script wraps the release binary into `TuneSort.app`, with an Info.plist
  (bundle id, `NSAppleEventsUsageDescription`) and an ad-hoc signature. Where it lives
  needs the user's OK (see open decisions).

## Testing

Tests are written by the `test-writer` agent from this spec and the public interfaces,
never from the implementation. Stubs come first, and the new tests must fail for the
right reason before implementation.

**Python** (pytest, `tests/`, existing fakes in `tests/conftest.py`)
- **Core additions:** `should_stop` and `Report.cancelled`, `on_done`,
  `Cache.entries`, `Cache.delete`, `config.save_order`, and the tracks lookup.
- **`serve`:** built like `make_app`, as a function taking input and output streams plus
  factories for Music, sources and the cache. Tests feed it JSON lines and check the
  replies: every command, every error kind, `busy`, and cancel. Cancel tests use a fake
  source that waits on a `threading.Event`, not timing.
- These run in the existing CI.

**Swift** (XCTest, `mac/Tests/`)
- **`TuneSortCore`:** request and reply encoding, matching replies to requests, handling
  progress events, and how the client reacts to the helper crashing or speaking another
  protocol version. Also the view models: sidebar, song-table states, side panel and
  settings. All of it runs against a fake helper.
- **Views:** not unit-tested. They are checked by running the app against a scratch cache
  with dry runs. Real Music changes happen only with the user's go-ahead.
- Run locally only. CI stays Python-only for v1.

## Out of scope for v1

- Drag and drop
- Removing songs from playlists (including moving a re-tuned song)
- A menu-bar mode
- Signing, notarization or distribution
- Keeping comments in `config.toml`
- Swift tests in CI
- Any change to how sources are looked up

## Open decisions (need the user's OK)

1. **Where the build script goes.** The repo has no scripts folder; the user's rule is to
   ask before creating one. Options: `scripts/build-mac-app` (which could later hold
   `scripts/check`) or `mac/build-app.sh` inside the Swift project.
2. **The test writer's guard.** It allows only test, type-check and lint commands, so it
   probably blocks `swift test`. Delegating Swift tests needs the user to allow it there.
   Until then, no Swift tests can be written, because the implementer doesn't write tests.
3. **Install Xcode.** The user does this: App Store, then
   `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` and
   `sudo xcodebuild -license accept`.
