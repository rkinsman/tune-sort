"""Command-line interface: `tune-sort`.

  tune-sort playlists
      Print each playlist name on its own line.

  tune-sort bass sort|review|set ...
  tune-sort guitar sort|review|set ...
      The commands below, for one instrument. Each instrument has its own cache entries
      and review queue, its own playlists ("Bass – …" or "Guitar – …") and its own
      sources (see tune_sort.sources). Usage below omits the instrument: "sort PLAYLIST"
      means "tune-sort bass sort PLAYLIST" or "tune-sort guitar sort PLAYLIST".
      In prompts the example tuning is "(e.g. Drop D or B E A D G)" for bass and
      "(e.g. Drop D or D A D G B E)" for guitar.

  sort PLAYLIST [--dry-run] [--source both|ug|songsterr] [--review/--no-review]
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
      If any songs need review, it then asks "Review <n> songs now? [y/N]" (default No).
      --review skips the question and reviews; --no-review skips the question and doesn't.
      Reviewing goes through this run's songs that need review, exactly as `review` does
      (same output and answers). If at least one was answered, the playlist is sorted
      again with the same --dry-run and --source, printing the same per-track lines and
      summary, so the answered songs are added to their playlists.

  review
      For each queued song print "<artist> – <title>", then numbered candidates
      "  <i>) <tuning name> (<notes>) → <playlist name> (<source>: <matched artist> – "
      "<matched title>)", where <notes> is Tuning.notes; the " (<notes>)" part is left out
      when the name already is the notes. The playlist name shows the string count. Or
      "  No tunings found." when there are none, then prompt:
          "Choose 1-<n>, type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"
          "Type a tuning (e.g. Drop D or B E A D G), s to skip, q to quit"  (no candidates)
      An answer is a candidate number, a tuning (anything tuning.parse_name accepts),
      "s" to skip or "q" to quit. A typed tuning overrides the candidates. A chosen tuning
      is stored as a confirmed "manual" entry and confirmed with
      "Set <artist> – <title> to <tuning name> (<playlist name>)".
      An answer that isn't understood prints a message and asks again.
      Prints "Nothing to review." when the queue is empty.

  set ARTIST TITLE TUNING
      Store a confirmed "manual" entry and print
      "Set <artist> – <title> to <tuning name> (<playlist name>)".
      Exits 1 with a message if TUNING isn't understood.

While `sort` works, a spinner showing "[<i>/<n>] Looking up <artist> – <title>" is drawn
on stderr, but only when stderr is a terminal; it is removed when the sort finishes.
Otherwise (pipes, tests) nothing extra is printed.

Every command accepts --cache PATH (default: $TUNE_SORT_CACHE, else
~/.cache/tune-sort/tunings.db).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from tune_sort.cache import DEFAULT_PATH, Cache, Entry, ReviewItem
from tune_sort.matching import normalise_artist, normalise_title
from tune_sort.music import Music, MusicError, Track
from tune_sort.sorter import Report, sort_playlist
from tune_sort.sources import Source
from tune_sort.tuning import INSTRUMENTS, Instrument, Tuning, TuningParseError, parse_name

# Given the instrument and "both", "ug" or "songsterr", returns the sources to ask, in order.
SourcesFactory = Callable[[Instrument, str], list[Source]]


class SourceChoice(StrEnum):
    both = "both"
    ug = "ug"
    songsterr = "songsterr"


CACHE_OPTION = typer.Option(
    DEFAULT_PATH, "--cache", envvar="TUNE_SORT_CACHE", help="Tuning cache file."
)


def default_sources(instrument: Instrument, which: str) -> list[Source]:
    from tune_sort.http import make_fetch
    from tune_sort.sources.songsterr import Songsterr
    from tune_sort.sources.ultimate_guitar import UltimateGuitar

    fetch = make_fetch()
    chosen: list[Source] = []
    if which in ("both", "ug"):
        chosen.append(UltimateGuitar(fetch, instrument))
    if which in ("both", "songsterr"):
        chosen.append(Songsterr(fetch, instrument))
    return chosen


def make_app(music: Callable[[], Music], sources: SourcesFactory) -> typer.Typer:
    """Build the CLI with the given Music and sources factories, so tests can pass fakes."""
    app = typer.Typer(no_args_is_help=True, add_completion=False)

    @app.command()
    def playlists(cache_path: Path = CACHE_OPTION) -> None:  # noqa: ARG001 - uniform options
        """List your playlists."""
        for name in music().list_playlists():
            typer.echo(name)

    for instrument in INSTRUMENTS:
        app.add_typer(
            _instrument_app(instrument, music, sources),
            name=instrument,
            help=f"Sort, review and set {instrument} tunings.",
        )
    return app


def _instrument_app(
    instrument: Instrument, music: Callable[[], Music], sources: SourcesFactory
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True)

    @app.command()
    def sort(
        playlist: str,
        dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
        source: SourceChoice = typer.Option(SourceChoice.both, "--source"),
        review: Optional[bool] = typer.Option(
            None, "--review/--no-review", help="Review songs that need it without asking."
        ),
        cache_path: Path = CACHE_OPTION,
    ) -> None:
        """Sort PLAYLIST's songs into one playlist per tuning."""
        cache = Cache(cache_path, instrument)
        try:
            chosen = sources(instrument, source.value)
            report = _sort_and_print(music(), playlist, chosen, cache, dry_run)
            if not report.review:
                return
            if review is None:
                review = _confirm(f"Review {len(report.review)} songs now?")
            if not review:
                return
            keys = {_song_key(t.artist, t.name) for t in report.review}
            items = [i for i in cache.review_items() if _song_key(i.artist, i.title) in keys]
            if _review_items(cache, items):
                typer.echo("")
                _sort_and_print(music(), playlist, chosen, cache, dry_run)
        finally:
            cache.close()

    @app.command("review")
    def review_command(cache_path: Path = CACHE_OPTION) -> None:
        """Answer the songs that couldn't be sorted automatically."""
        cache = Cache(cache_path, instrument)
        try:
            items = cache.review_items()
            if not items:
                typer.echo("Nothing to review.")
                return
            _review_items(cache, items)
        finally:
            cache.close()

    @app.command("set")
    def set_tuning(artist: str, title: str, tuning: str, cache_path: Path = CACHE_OPTION) -> None:
        """Set a song's tuning by hand, e.g. set "Tool" "Schism" "Drop D"."""
        try:
            parsed = parse_name(tuning, instrument)
        except TuningParseError as e:
            typer.echo(f"Error: tuning not understood: {tuning!r} ({e})", err=True)
            raise typer.Exit(1) from e
        cache = Cache(cache_path, instrument)
        try:
            cache.put(artist, title, Entry(parsed, "manual", confirmed=True))
        finally:
            cache.close()
        typer.echo(f"Set {artist} – {title} to {_described(parsed)}")

    return app


TUNING_EXAMPLES = {"bass": "(e.g. Drop D or B E A D G)", "guitar": "(e.g. Drop D or D A D G B E)"}


def _sort_and_print(
    music: Music, playlist: str, sources: list[Source], cache: Cache, dry_run: bool
) -> Report:
    try:
        console = Console(stderr=True)
        if console.is_terminal:
            # Text, not markup: "[3/22]" and song titles may contain brackets.
            with console.status(Text(f"Reading {playlist} from Music…")) as status:

                def show(i: int, total: int, track: Track) -> None:
                    status.update(Text(f"[{i}/{total}] Looking up {track.artist} – {track.name}…"))

                report = sort_playlist(music, playlist, sources, cache, dry_run, show)
        else:
            report = sort_playlist(music, playlist, sources, cache, dry_run)
    except MusicError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e

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
    return report


def _review_items(cache: Cache, items: list[ReviewItem]) -> int:
    """Ask about each item and store the answers. Returns how many were answered."""
    answered = 0
    for item in items:
        typer.echo(f"\n{item.artist} – {item.title}")
        if not item.candidates:
            typer.echo("  No tunings found.")
        for i, m in enumerate(item.candidates, 1):
            typer.echo(
                f"  {i}) {_with_notes(m.tuning)} → {m.tuning.playlist_name} "
                f"({m.source}: {m.matched_artist} – {m.matched_title})"
            )
        chosen = _ask_tuning(
            len(item.candidates), [m.tuning for m in item.candidates], cache.instrument
        )
        if chosen == "q":
            break
        if isinstance(chosen, Tuning):
            cache.put(item.artist, item.title, Entry(chosen, "manual", confirmed=True))
            typer.echo(f"Set {item.artist} – {item.title} to {_described(chosen)}")
            answered += 1
    return answered


def _song_key(artist: str, title: str) -> tuple[str, str]:
    return normalise_artist(artist), normalise_title(title)


def _confirm(question: str) -> bool:
    """Ask a yes/no question, defaulting to No, and treating end of input as No."""
    try:
        return bool(typer.confirm(question, default=False))
    except (typer.Abort, EOFError):
        typer.echo("")
        return False


def _with_notes(tuning: Tuning) -> str:
    """E.g. "B Standard (B E A D)"; just the notes when they already are the name."""
    if tuning.name == tuning.notes:
        return tuning.name
    return f"{tuning.name} ({tuning.notes})"


def _described(tuning: Tuning) -> str:
    return f"{tuning.name} ({tuning.playlist_name})"


def _ask_tuning(count: int, candidates: list[Tuning], instrument: Instrument) -> Optional[object]:
    """Prompt until the answer is a candidate number, a tuning, "s" (None) or "q"."""
    while True:
        choose = f"Choose 1-{count}, type a tuning" if count else "Type a tuning"
        examples = TUNING_EXAMPLES[instrument]
        answer = str(typer.prompt(f"{choose} {examples}, s to skip, q to quit")).strip()
        lowered = answer.lower()
        if lowered == "s":
            return None
        if lowered == "q":
            return "q"
        if answer.isdigit() and 1 <= int(answer) <= count:
            return candidates[int(answer) - 1]
        try:
            return parse_name(answer, instrument)
        except TuningParseError:
            typer.echo(f"Not understood: {answer!r}. Try e.g. 1, Drop D, E A D G, s or q.")


def main() -> None:
    from tune_sort.cache import migrate_legacy_cache
    from tune_sort.music import AppleMusic

    if migrate_legacy_cache():
        typer.echo("Moved your tuning cache to ~/.cache/tune-sort/.", err=True)

    make_app(AppleMusic, default_sources)()
