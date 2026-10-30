"""config.save_order."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tune_sort.config import DEFAULT_ORDER, ConfigError, load_order, save_order

BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]
GUITAR_DEFAULT = ["ug-pro", "ug-tab", "songsterr"]


def test_save_creates_file_and_dirs(tmp_path):
    path = tmp_path / "a" / "b" / "config.toml"
    result = save_order("bass", ["songsterr", "ug-bass"], path)
    assert result == ["songsterr", "ug-bass"]
    assert path.is_file()
    assert load_order("bass", path) == ["songsterr", "ug-bass"]
    assert load_order("guitar", path) == GUITAR_DEFAULT


def test_save_keeps_other_instrument(tmp_path):
    path = tmp_path / "config.toml"
    save_order("bass", ["songsterr"], path)
    result = save_order("guitar", ["ug-tab", "ug-pro"], path)
    assert result == ["ug-tab", "ug-pro"]
    assert load_order("bass", path) == ["songsterr"]
    assert load_order("guitar", path) == ["ug-tab", "ug-pro"]
    save_order("bass", ["ug-bass", "songsterr"], path)
    assert load_order("guitar", path) == ["ug-tab", "ug-pro"]
    assert load_order("bass", path) == ["ug-bass", "songsterr"]


def test_save_none_resets_to_default(tmp_path):
    path = tmp_path / "config.toml"
    save_order("bass", ["songsterr"], path)
    save_order("guitar", ["ug-tab"], path)
    result = save_order("bass", None, path)
    assert result == BASS_DEFAULT
    assert load_order("bass", path) == list(DEFAULT_ORDER["bass"])
    assert load_order("guitar", path) == ["ug-tab"]


def test_save_none_without_file(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    assert save_order("guitar", None, path) == GUITAR_DEFAULT
    assert load_order("guitar", path) == GUITAR_DEFAULT


@pytest.mark.parametrize(
    "instrument,order",
    [
        ("bass", ["songsterr", "banana"]),
        ("bass", ["ug-tab"]),
        ("guitar", ["ug-bass"]),
        ("bass", []),
        ("guitar", []),
        ("bass", ["songsterr", "songsterr"]),
    ],
)
def test_save_invalid_order_raises_and_leaves_file(tmp_path, instrument, order):
    path = tmp_path / "config.toml"
    original = b'[bass]\norder = ["songsterr", "ug-bass"]\n'
    path.write_bytes(original)
    with pytest.raises(ConfigError):
        save_order(instrument, order, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("order", [["banana"], [], ["songsterr", "songsterr"]])
def test_save_invalid_order_does_not_create_file(tmp_path, order):
    path = tmp_path / "newdir" / "config.toml"
    with pytest.raises(ConfigError):
        save_order("bass", order, path)
    assert not path.exists()


@pytest.mark.parametrize(
    "text",
    [
        '[other]\nx = 1\n',
        '[bass]\ncolour = 1\n',
        '[bass]\norder = ["songsterr"]\ncolour = 1\n',
        'top = 1\n',
    ],
)
def test_save_refuses_unknown_content(tmp_path, text):
    path = tmp_path / "config.toml"
    original = text.encode("utf-8")
    path.write_bytes(original)
    with pytest.raises(ConfigError):
        save_order("guitar", ["ug-tab"], path)
    assert path.read_bytes() == original


def test_save_refuses_invalid_toml(tmp_path):
    path = tmp_path / "config.toml"
    original = b"[bass\norder = "
    path.write_bytes(original)
    with pytest.raises(ConfigError):
        save_order("bass", ["songsterr"], path)
    assert path.read_bytes() == original


def test_save_written_file_is_valid_toml(tmp_path):
    path = tmp_path / "config.toml"
    save_order("bass", ["songsterr", "ug-pro"], path)
    save_order("guitar", ["ug-tab"], path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    assert data == {
        "bass": {"order": ["songsterr", "ug-pro"]},
        "guitar": {"order": ["ug-tab"]},
    }


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "config.toml"
    save_order("bass", ["songsterr"], path)
    assert [p.name for p in Path(tmp_path).iterdir()] == ["config.toml"]
