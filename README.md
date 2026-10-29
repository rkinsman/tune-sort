# tune-sort

Sorts an Apple Music playlist into playlists by the tuning the bass is played in, such as
`Bass – Drop D`, `Bass – Eb Standard` or `Bass 5-String – B Standard`.

Each song's tuning is looked up from public pages, in this order:

1. Ultimate Guitar: the highest-rated Pro tab whose only instrument is bass
2. Ultimate Guitar: the highest-rated Bass tab
3. Songsterr: the song's bass track

Every source is asked, so Ultimate Guitar's answer is double-checked against Songsterr. If two
sources both match the song exactly but disagree on the tuning, the song goes to a review queue.
Songs that can't be matched exactly go to the review queue too. Answers are cached in
`~/.cache/tune-sort/tunings.db`, so each song is only looked up once.

Running `sort` again is safe. It reuses the existing playlists, never adds a song twice,
and only looks up songs it hasn't seen before.

Only macOS is supported, because the app talks to the Music app through `osascript`. It
needs no Apple Developer or Ultimate Guitar account.

## Setup

Needs [uv](https://docs.astral.sh/uv/) (`brew install uv`). It fetches Python 3.12 and the
dependencies:

```bash
uv sync
```

## Usage

```bash
uv run tune-sort playlists
uv run tune-sort sort "My Playlist" --dry-run   # show what would happen
uv run tune-sort sort "My Playlist"             # create playlists and add songs
uv run tune-sort review                         # answer songs that couldn't be matched
uv run tune-sort set "Nirvana" "Come As You Are" "D Standard"
```

`--source ug|songsterr|both` limits which sites are asked. The default is `both`.

While sorting, a spinner shows which song is being looked up (`[3/22] Looking up …`). If
any songs need review at the end, `sort` offers to review them right away (`--review` or
`--no-review` skip the question).

Tunings can be typed as names, for example `Drop D`, `eb standard` or
`5-string B Standard`, or as notes from the lowest string up, for example `D A D G`.
Enharmonic spellings are treated as the same tuning, so D# G# C# F# and Eb Ab Db Gb
both land in `Bass – Eb Standard`.

## Development

```bash
uv run pytest
uv run ruff check src tests
uv run mypy src tests
```
