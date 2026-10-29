from __future__ import annotations

from pathlib import Path

import pytest

from tune_sort.config import (
    CONFIG_PATH,
    DEFAULT_ORDER,
    SOURCE_NAMES,
    ConfigError,
    load_order,
    parse_order,
)

BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]
GUITAR_DEFAULT = ["ug-pro", "ug-tab", "songsterr"]


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_constants():
    assert CONFIG_PATH == Path.home() / ".config" / "tune-sort" / "config.toml"
    assert tuple(SOURCE_NAMES["bass"]) == ("ug-pro", "ug-bass", "songsterr")
    assert tuple(SOURCE_NAMES["guitar"]) == ("ug-pro", "ug-tab", "songsterr")
    assert list(DEFAULT_ORDER["bass"]) == BASS_DEFAULT
    assert list(DEFAULT_ORDER["guitar"]) == GUITAR_DEFAULT


def test_config_error_is_value_error():
    assert issubclass(ConfigError, ValueError)


# ------------------------------------------------------------------- load_order


def test_missing_file_gives_defaults(tmp_path):
    path = tmp_path / "nope.toml"
    assert load_order("bass", path) == BASS_DEFAULT
    assert load_order("guitar", path) == GUITAR_DEFAULT
    assert not path.exists()


def test_missing_section_and_key_give_defaults(tmp_path):
    path = write(tmp_path, '[guitar]\norder = ["songsterr"]\n')
    assert load_order("bass", path) == BASS_DEFAULT
    path2 = write(tmp_path, "[bass]\nsomething = 1\n")
    assert load_order("bass", path2) == BASS_DEFAULT
    assert load_order("guitar", write(tmp_path, "")) == GUITAR_DEFAULT


def test_order_from_file_per_instrument(tmp_path):
    path = write(
        tmp_path,
        '[bass]\norder = ["songsterr", "ug-bass", "ug-pro"]\n\n'
        '[guitar]\norder = ["ug-tab", "songsterr", "ug-pro"]\n',
    )
    assert load_order("bass", path) == ["songsterr", "ug-bass", "ug-pro"]
    assert load_order("guitar", path) == ["ug-tab", "songsterr", "ug-pro"]


def test_order_may_leave_sources_out(tmp_path):
    path = write(tmp_path, '[bass]\norder = ["songsterr"]\n')
    assert load_order("bass", path) == ["songsterr"]


@pytest.mark.parametrize(
    "instrument,order",
    [
        ("bass", "[]"),
        ("bass", '["ug-tab"]'),
        ("bass", '["songsterr", "banana"]'),
        ("guitar", '["ug-bass"]'),
        ("guitar", "[]"),
        ("bass", '["songsterr", "songsterr"]'),
        ("guitar", '["ug-pro", "ug-tab", "ug-pro"]'),
        ("bass", '"songsterr"'),
        ("bass", "[1, 2]"),
        ("bass", '["songsterr", 2]'),
    ],
)
def test_invalid_order_raises(tmp_path, instrument, order):
    path = write(tmp_path, "[%s]\norder = %s\n" % (instrument, order))
    with pytest.raises(ConfigError):
        load_order(instrument, path)


def test_invalid_toml_raises_with_path_in_message(tmp_path):
    path = write(tmp_path, "[bass\norder = ")
    with pytest.raises(ConfigError) as info:
        load_order("bass", path)
    assert str(path) in str(info.value)


def test_invalid_order_message_includes_path(tmp_path):
    path = write(tmp_path, '[bass]\norder = ["ug-tab"]\n')
    with pytest.raises(ConfigError) as info:
        load_order("bass", path)
    assert str(path) in str(info.value)


def test_error_message_names_the_problem(tmp_path):
    path = write(tmp_path, '[bass]\norder = ["ug-tab"]\n')
    with pytest.raises(ConfigError) as info:
        load_order("bass", path)
    assert "ug-tab" in str(info.value)


# ------------------------------------------------------------------ parse_order


def test_parse_order_basic():
    assert parse_order("songsterr, ug-bass", "bass") == ["songsterr", "ug-bass"]
    assert parse_order("songsterr,ug-bass,ug-pro", "bass") == ["songsterr", "ug-bass", "ug-pro"]
    assert parse_order("  ug-pro ,  songsterr  ", "bass") == ["ug-pro", "songsterr"]
    assert parse_order("songsterr", "bass") == ["songsterr"]


def test_parse_order_guitar_names():
    assert parse_order("ug-tab, songsterr", "guitar") == ["ug-tab", "songsterr"]
    with pytest.raises(ConfigError):
        parse_order("ug-bass", "guitar")


@pytest.mark.parametrize("text", ["", "   ", "banana", "ug-tab", "songsterr,songsterr"])
def test_parse_order_invalid_for_bass(text):
    with pytest.raises(ConfigError):
        parse_order(text, "bass")
