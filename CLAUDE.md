# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

tune-sort sorts an Apple Music playlist into per-tuning playlists. The core is Python (`src/tune_sort/`). It has two front ends: the `tune-sort` CLI, and a SwiftUI Mac app in `mac/` that drives the core through a JSON-lines helper, `tune-sort serve`. It's macOS only, because it talks to Music through `osascript`.

## Commands

- **Python:** CI runs these three, on Ubuntu.
  - `uv run pytest` (one test: `uv run pytest tests/test_serve.py::test_hello`)
  - `uv run ruff check`
  - `uv run mypy src tests`
- **Swift:** run `swift build` and `swift test` from `mac/`. Needs Xcode. Runs locally only.
- **Shell:** `tests/shell/run` runs shellcheck on `scripts/*`, then the bats tests.
  - Bats is vendored as git submodules, so run `git submodule update --init` first.
  - It includes a release build of about a minute.
- **App bundle:** `scripts/build-mac-app [--out X.app]` builds it.

## Safety

- **Changing Music:** a real sort, creating playlists or adding tracks needs the user's go-ahead.
- **Trying things on real data:** use `--dry-run`, and scratch copies via `--cache` and `--config`. Debug app builds read the same flags from `TUNESORT_HELPER_ARGS`.
- **Ultimate Guitar:** public pages only, with no login. Getting past its paywall was refused, and that refusal stands.

## Things that aren't obvious from the code

- **`serve` threading:** only the main thread touches Music, the cache (its sqlite connections are single-threaded) and the sources. The stdin reader thread answers `cancel` and `busy` itself. End of input cancels a running sort.
- **The protocol:** `src/tune_sort/wire.py` and `mac/Sources/TuneSortCore/Models.swift` encode the same JSON shapes; change both together. The spec is `docs/superpowers/specs/2026-10-29-mac-app-design.md`.
- **Where the Mac app's logic lives:** in `TuneSortCore`, which is unit-tested with `FakeHelperAPI` and `FakeTransport`. The `TuneSort` target is views only and has no tests; check it by running the app.
- **SwiftUI pitfalls already hit here:**
  - `List(selection:)` tags must be the non-optional selection type.
  - `onHover` never fires inside `Table` cells; rows track the pointer with `PointerTracker` instead.
- **Python tests:** `tests/` is a package, so import helpers as `from tests.conftest import ...`.
