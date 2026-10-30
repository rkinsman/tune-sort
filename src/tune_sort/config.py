"""User configuration: the order tuning sources are asked in, per instrument.

The file is TOML, by default ~/.config/tune-sort/config.toml ($TUNE_SORT_CONFIG overrides):

    [bass]
    order = ["songsterr", "ug-bass", "ug-pro"]

    [guitar]
    order = ["ug-pro", "ug-tab", "songsterr"]

A missing file, or a missing section or `order` key, means the default order. An order
may leave sources out (they are then not asked) but must name at least one, only names
from SOURCE_NAMES[instrument], and none twice.
"""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

from tune_sort.tuning import Instrument

CONFIG_PATH = Path.home() / ".config" / "tune-sort" / "config.toml"

SOURCE_NAMES: dict[Instrument, tuple[str, ...]] = {
    "bass": ("ug-pro", "ug-bass", "songsterr"),
    "guitar": ("ug-pro", "ug-tab", "songsterr"),
}
# The default order is the order of SOURCE_NAMES.
DEFAULT_ORDER: dict[Instrument, tuple[str, ...]] = dict(SOURCE_NAMES)


class ConfigError(ValueError):
    """The config file or an --order value is invalid. The message says what is wrong."""


def load_order(instrument: Instrument, path: Path = CONFIG_PATH) -> list[str]:
    """The source order for `instrument` from the config file at `path`, or the default.
    Raises ConfigError for invalid TOML or an invalid order; the message includes the
    path."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return list(DEFAULT_ORDER[instrument])
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path}: {e}") from e
    section = data.get(instrument)
    if section is None:
        return list(DEFAULT_ORDER[instrument])
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: [{instrument}] must be a table")
    if "order" not in section:
        return list(DEFAULT_ORDER[instrument])
    try:
        return _validated(section["order"], instrument)
    except ConfigError as e:
        raise ConfigError(f"{path}: [{instrument}] order: {e}") from e


def save_order(
    instrument: Instrument, order: Optional[Sequence[str]], path: Path = CONFIG_PATH
) -> list[str]:
    """Save `order` as the source order for `instrument` in the config file at `path`,
    creating the file and its directories if needed and keeping the other instrument's
    order. `order` None resets `instrument` to the default order. Returns the effective
    order afterwards, as load_order would.

    Raises ConfigError, leaving the file untouched, if `order` is invalid or the existing
    file is not valid TOML or holds anything but [bass] and [guitar] tables with only an
    `order` key (rewriting it would lose that content). The write is atomic."""
    checked = None if order is None else _validated(list(order), instrument)
    orders: dict[Instrument, list[str]] = {}
    try:
        text: Optional[str] = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = None
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"{path}: {e}") from e
    if text is not None:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from e
        for key, section in data.items():
            if (
                key not in SOURCE_NAMES
                or not isinstance(section, dict)
                or not set(section) <= {"order"}
            ):
                raise ConfigError(
                    f"{path}: refusing to rewrite a file with content other than "
                    "[bass] and [guitar] order keys"
                )
        for inst in SOURCE_NAMES:
            if inst != instrument and "order" in data.get(inst, {}):
                try:
                    orders[inst] = _validated(data[inst]["order"], inst)
                except ConfigError as e:
                    raise ConfigError(f"{path}: [{inst}] order: {e}") from e
    if checked is not None:
        orders[instrument] = checked
    out = ""
    for inst in SOURCE_NAMES:
        if inst in orders:
            names = ", ".join(json.dumps(n) for n in orders[inst])
            out += f"[{inst}]\norder = [{names}]\n\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(out)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        raise ConfigError(f"{path}: {e}") from e
    return list(checked) if checked is not None else list(DEFAULT_ORDER[instrument])


def parse_order(text: str, instrument: Instrument) -> list[str]:
    """Parse an --order value: comma-separated source names, spaces allowed
    ("songsterr, ug-bass"). Raises ConfigError if invalid, as for the file."""
    if not text.strip():
        raise ConfigError("no sources given")
    return _validated([name.strip() for name in text.split(",")], instrument)


def _validated(order: Any, instrument: Instrument) -> list[str]:
    allowed = SOURCE_NAMES[instrument]
    if not isinstance(order, list) or not all(isinstance(n, str) for n in order):
        raise ConfigError("must be a list of source names")
    if not order:
        raise ConfigError("must name at least one source")
    for name in order:
        if name not in allowed:
            raise ConfigError(
                f"unknown source {name!r} for {instrument} (choose from {', '.join(allowed)})"
            )
    duplicates = sorted({n for n in order if order.count(n) > 1})
    if duplicates:
        raise ConfigError(f"{', '.join(duplicates)} named more than once")
    return list(order)
