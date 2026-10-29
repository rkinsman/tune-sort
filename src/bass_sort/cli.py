"""Command-line interface: `bass-sort`.

  bass-sort playlists
      Print each playlist name on its own line.

  bass-sort sort PLAYLIST [--dry-run] [--source both|ug|songsterr]
      Resolve each track and print one line per track:
          "<artist> – <title> → <playlist name> (<source>)"  or
          "<artist> – <title> → needs review"
      then a summary:
          "Created playlist: <name>"           ("Would create playlist: <name>" with --dry-run)
          "Added <n> to <playlist>"            ("Would add <n> to <playlist>" with --dry-run)
          "Already present: <n>"
          "Needs review: <n>"
      --source both (default) asks UG then Songsterr. Exits 1 with a message if PLAYLIST
      doesn't exist.

  bass-sort review
      For each queued song print "<artist> – <title>", then numbered candidates
      "  <i>) <tuning name> (<source>: <matched artist> – <matched title>)", then prompt.
      An answer is a candidate number, a tuning (anything tuning.parse_name accepts),
      "s" to skip or "q" to quit. A chosen tuning is stored as a confirmed "manual" entry.
      An answer that isn't understood prints a message and asks again.
      Prints "Nothing to review." when the queue is empty.

  bass-sort set ARTIST TITLE TUNING
      Store a confirmed "manual" entry and print "Set <artist> – <title> to <tuning name>".
      Exits 1 with a message if TUNING isn't understood.

Every command accepts --cache PATH (default: $BASS_SORT_CACHE, else
~/.cache/bass-tuning-sorter/tunings.db).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Optional

import typer

from bass_sort.cache import DEFAULT_PATH, Cache, Entry
from bass_sort.music import Music, MusicError
from bass_sort.sorter import sort_playlist
from bass_sort.sources import Source
from bass_sort.tuning import Tuning, TuningParseError, parse_name

# Given "both", "ug" or "songsterr", returns the sources to ask, in order.
SourcesFactory = Callable[[str], list[Source]]


class SourceChoice(StrEnum):
    both = "both"
    ug = "ug"
    songsterr = "songsterr"


CACHE_OPTION = typer.Option(
    DEFAULT_PATH, "--cache", envvar="BASS_SORT_CACHE", help="Tuning cache file."
)


def default_sources(which: str) -> list[Source]:
    from bass_sort.http import make_fetch
    from bass_sort.sources.songsterr import Songsterr
    from bass_sort.sources.ultimate_guitar import UltimateGuitar

    fetch = make_fetch()
    chosen: list[Source] = []
    if which in ("both", "ug"):
        chosen.append(UltimateGuitar(fetch))
    if which in ("both", "songsterr"):
        chosen.append(Songsterr(fetch))
    return chosen


def make_app(music: Callable[[], Music], sources: SourcesFactory) -> typer.Typer:
    """Build the CLI with the given Music and sources factories, so tests can pass fakes."""
    app = typer.Typer(no_args_is_help=True, add_completion=False)

    @app.command()
    def playlists(cache_path: Path = CACHE_OPTION) -> None:  # noqa: ARG001 - uniform options
        """List your playlists."""
        for name in music().list_playlists():
            typer.echo(name)

    @app.command()
    def sort(
        playlist: str,
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
        source: SourceChoice = typer.Option(SourceChoice.both, "--source"),
        cache_path: Path = CACHE_OPTION,
    ) -> None:
        """Sort PLAYLIST's songs into one playlist per bass tuning."""
        cache = Cache(cache_path)
        try:
            report = sort_playlist(music(), playlist, sources(source.value), cache, dry_run)
        except MusicError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1) from e
        finally:
            cache.close()

        for track, res in report.resolutions:
            song = f"{track.artist} – {track.name}"
            if res.tuning is None:
                typer.echo(f"{song} → needs review")
            else:
                typer.echo(f"{song} → {res.tuning.playlist_name} ({res.source})")
        typer.echo("")
        created = "Would create playlist" if dry_run else "Created playlist"
        for name in report.created_playlists:
            typer.echo(f"{created}: {name}")
        verb = "Would add" if dry_run else "Added"
        for name, tracks in report.added.items():
            typer.echo(f"{verb} {len(tracks)} to {name}")
        typer.echo(f"Already present: {sum(len(t) for t in report.already_present.values())}")
        typer.echo(f"Needs review: {len(report.review)}")

    @app.command()
    def review(cache_path: Path = CACHE_OPTION) -> None:
        """Answer the songs that couldn't be sorted automatically."""
        cache = Cache(cache_path)
        try:
            items = cache.review_items()
            if not items:
                typer.echo("Nothing to review.")
                return
            for item in items:
                typer.echo(f"\n{item.artist} – {item.title}")
                for i, m in enumerate(item.candidates, 1):
                    typer.echo(
                        f"  {i}) {m.tuning.name} ({m.source}: {m.matched_artist} – "
                        f"{m.matched_title})"
                    )
                chosen = _ask_tuning(len(item.candidates), [m.tuning for m in item.candidates])
                if chosen == "q":
                    break
                if isinstance(chosen, Tuning):
                    cache.put(item.artist, item.title, Entry(chosen, "manual", confirmed=True))
                    typer.echo(f"Set {item.artist} – {item.title} to {chosen.name}")
        finally:
            cache.close()

    @app.command("set")
    def set_tuning(artist: str, title: str, tuning: str, cache_path: Path = CACHE_OPTION) -> None:
        """Set a song's tuning by hand, e.g. set "Tool" "Schism" "Drop D"."""
        try:
            parsed = parse_name(tuning)
        except TuningParseError as e:
            typer.echo(f"Error: tuning not understood: {tuning!r} ({e})", err=True)
            raise typer.Exit(1) from e
        cache = Cache(cache_path)
        try:
            cache.put(artist, title, Entry(parsed, "manual", confirmed=True))
        finally:
            cache.close()
        typer.echo(f"Set {artist} – {title} to {parsed.name}")

    return app


def _ask_tuning(count: int, candidates: list[Tuning]) -> Optional[object]:
    """Prompt until the answer is a candidate number, a tuning, "s" (None) or "q"."""
    while True:
        answer = str(typer.prompt("Number, tuning, s to skip, q to quit")).strip()
        lowered = answer.lower()
        if lowered == "s":
            return None
        if lowered == "q":
            return "q"
        if answer.isdigit() and 1 <= int(answer) <= count:
            return candidates[int(answer) - 1]
        try:
            return parse_name(answer)
        except TuningParseError:
            typer.echo(f"Not understood: {answer!r}. Try e.g. 1, Drop D, E A D G, s or q.")


def main() -> None:
    from bass_sort.music import AppleMusic

    make_app(AppleMusic, default_sources)()
