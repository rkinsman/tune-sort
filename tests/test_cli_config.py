"""CLI source ordering: the config file, --order, --source and the `config` command."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest
from conftest import FakeMusic, FakeSource, make_match, make_track
from typer.testing import CliRunner

from tune_sort.cli import make_app

DASH = "–"
BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]
GUITAR_DEFAULT = ["ug-pro", "ug-tab", "songsterr"]

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Nobody", "Nothing")

runner = CliRunner()


class Factory:
    def __init__(self, instrument: str = "bass") -> None:
        self.requested: List[Tuple[str, List[str]]] = []
        self.sources = [
            FakeSource(
                "s",
                {
                    ("Tool", "Schism"): make_match(
                        "D A D G B E" if instrument == "guitar" else "D A D G",
                        "ug-pro" if instrument == "guitar" else "ug-bass",
                        instrument=instrument,
                    )
                },
            )
        ]

    def __call__(self, instrument: str, names: Any) -> Any:
        self.requested.append((instrument, list(names)))
        return self.sources


def write_config(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def run_sort(
    tmp_path,
    instrument: str,
    extra: List[str],
    config: Optional[Any] = "missing",
    env: Optional[Dict[str, str]] = None,
    input: Optional[str] = None,
    music: Optional[FakeMusic] = None,
):
    factory = Factory(instrument)
    music = music or FakeMusic({"Road": [A]})
    app = make_app(lambda: music, factory)
    args = [instrument, "sort", "Road"] + extra
    if config == "missing":
        args += ["--config", str(tmp_path / "missing.toml")]
    elif config is not None:
        args += ["--config", str(config)]
    args += ["--cache", str(tmp_path / "c.db")]
    result = runner.invoke(app, args, env=env, input=input)
    return result, factory, music


def run_config(tmp_path, args: List[str], env: Optional[Dict[str, str]] = None):
    app = make_app(lambda: FakeMusic(), Factory())
    return runner.invoke(app, ["config"] + args, env=env)


# ------------------------------------------------------------ default order


def test_default_order_bass(tmp_path):
    result, factory, _ = run_sort(tmp_path, "bass", [])
    assert result.exit_code == 0, result.output
    assert factory.requested == [("bass", BASS_DEFAULT)]


def test_default_order_guitar(tmp_path):
    result, factory, _ = run_sort(tmp_path, "guitar", [])
    assert result.exit_code == 0, result.output
    assert factory.requested == [("guitar", GUITAR_DEFAULT)]


# --------------------------------------------------------------- config file


def test_config_file_order_reaches_factory_per_instrument(tmp_path):
    cfg = write_config(
        tmp_path,
        '[bass]\norder = ["songsterr", "ug-bass", "ug-pro"]\n\n'
        '[guitar]\norder = ["ug-tab", "songsterr"]\n',
    )
    _, bass_factory, _ = run_sort(tmp_path, "bass", [], config=cfg)
    assert bass_factory.requested == [("bass", ["songsterr", "ug-bass", "ug-pro"])]
    _, guitar_factory, _ = run_sort(tmp_path, "guitar", [], config=cfg)
    assert guitar_factory.requested == [("guitar", ["ug-tab", "songsterr"])]


def test_config_file_for_one_instrument_leaves_other_default(tmp_path):
    cfg = write_config(tmp_path, '[bass]\norder = ["songsterr"]\n')
    _, factory, _ = run_sort(tmp_path, "guitar", [], config=cfg)
    assert factory.requested == [("guitar", GUITAR_DEFAULT)]


def test_order_flag_overrides_config_file(tmp_path):
    cfg = write_config(tmp_path, '[bass]\norder = ["songsterr", "ug-bass", "ug-pro"]\n')
    result, factory, _ = run_sort(
        tmp_path, "bass", ["--order", "ug-bass, songsterr"], config=cfg
    )
    assert result.exit_code == 0, result.output
    assert factory.requested == [("bass", ["ug-bass", "songsterr"])]


def test_order_flag_without_config_file(tmp_path):
    _, factory, _ = run_sort(tmp_path, "bass", ["--order", "songsterr,ug-bass,ug-pro"])
    assert factory.requested == [("bass", ["songsterr", "ug-bass", "ug-pro"])]


def test_guitar_order_flag(tmp_path):
    _, factory, _ = run_sort(tmp_path, "guitar", ["--order", "songsterr,ug-tab"])
    assert factory.requested == [("guitar", ["songsterr", "ug-tab"])]


# --------------------------------------------------------------- --source


def test_source_ug_keeps_ug_names_in_order(tmp_path):
    _, factory, _ = run_sort(
        tmp_path, "bass", ["--order", "songsterr,ug-bass,ug-pro", "--source", "ug"]
    )
    assert factory.requested == [("bass", ["ug-bass", "ug-pro"])]


def test_source_songsterr_keeps_only_songsterr(tmp_path):
    _, factory, _ = run_sort(tmp_path, "bass", ["--source", "songsterr"])
    assert factory.requested == [("bass", ["songsterr"])]


def test_source_both_keeps_everything(tmp_path):
    _, factory, _ = run_sort(tmp_path, "bass", ["--source", "both"])
    assert factory.requested == [("bass", BASS_DEFAULT)]


def test_source_ug_for_guitar(tmp_path):
    _, factory, _ = run_sort(tmp_path, "guitar", ["--source", "ug"])
    assert factory.requested == [("guitar", ["ug-pro", "ug-tab"])]


def test_source_filter_applies_to_config_order(tmp_path):
    cfg = write_config(tmp_path, '[bass]\norder = ["songsterr", "ug-pro"]\n')
    _, factory, _ = run_sort(tmp_path, "bass", ["--source", "ug"], config=cfg)
    assert factory.requested == [("bass", ["ug-pro"])]


def test_no_sources_left_exits_1(tmp_path):
    music = FakeMusic({"Road": [A]})
    result, _, _ = run_sort(
        tmp_path, "bass", ["--order", "songsterr", "--source", "ug"], music=music
    )
    assert result.exit_code == 1
    assert "no sources left" in result.output
    assert music.add_calls == []
    assert music.ensure_calls == []


# ------------------------------------------------------------ invalid input


@pytest.mark.parametrize("order", ["ug-tab", "banana", "songsterr,songsterr", "ug-bass,,ug-pro"])
def test_invalid_order_flag_exits_1(tmp_path, order):
    music = FakeMusic({"Road": [A]})
    result, _, _ = run_sort(tmp_path, "bass", ["--order", order], music=music)
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert music.add_calls == []


def test_guitar_rejects_bass_source_name(tmp_path):
    result, _, _ = run_sort(tmp_path, "guitar", ["--order", "ug-bass"])
    assert result.exit_code == 1
    assert "Error:" in result.output


@pytest.mark.parametrize(
    "text",
    [
        "[bass\norder = ",
        '[bass]\norder = ["ug-tab"]\n',
        '[bass]\norder = "songsterr"\n',
        "[bass]\norder = []\n",
    ],
)
def test_invalid_config_file_exits_1(tmp_path, text):
    cfg = write_config(tmp_path, text)
    music = FakeMusic({"Road": [A]})
    result, _, _ = run_sort(tmp_path, "bass", [], config=cfg, music=music)
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert music.add_calls == []


def test_valid_order_flag_beats_invalid_config_is_not_required_but_exit_code_is_error(tmp_path):
    # An invalid config file is reported even when --order is not given.
    cfg = write_config(tmp_path, "not toml [")
    result, _, _ = run_sort(tmp_path, "bass", [], config=cfg)
    assert result.exit_code == 1


# ------------------------------------------------------------- review re-sort


def test_review_resort_uses_same_names(tmp_path):
    cfg = write_config(tmp_path, '[bass]\norder = ["songsterr", "ug-bass"]\n')
    music = FakeMusic({"Road": [A, B]})
    result, factory, _ = run_sort(
        tmp_path, "bass", ["--review"], config=cfg, input="Drop D\n", music=music
    )
    assert result.exit_code == 0, result.output
    assert music.playlists["Bass %s Drop D" % DASH] == [A, B]
    assert len(factory.requested) >= 1
    assert all(r == ("bass", ["songsterr", "ug-bass"]) for r in factory.requested)


def test_review_resort_uses_same_names_with_order_and_source(tmp_path):
    music = FakeMusic({"Road": [A, B]})
    _, factory, _ = run_sort(
        tmp_path,
        "bass",
        ["--order", "songsterr,ug-bass,ug-pro", "--source", "ug", "--review"],
        input="s\n",
        music=music,
    )
    assert factory.requested
    assert all(r == ("bass", ["ug-bass", "ug-pro"]) for r in factory.requested)


# ----------------------------------------------------------- config command


def test_config_command_without_file(tmp_path):
    path = tmp_path / "missing.toml"
    result = run_config(tmp_path, ["--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "Config file: %s" % path in result.output
    assert "(not found, using defaults)" in result.output
    assert "bass: ug-pro, ug-bass, songsterr" in result.output
    assert "guitar: ug-pro, ug-tab, songsterr" in result.output


def test_config_command_with_file(tmp_path):
    path = write_config(
        tmp_path,
        '[bass]\norder = ["songsterr", "ug-bass"]\n\n[guitar]\norder = ["ug-tab"]\n',
    )
    result = run_config(tmp_path, ["--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "Config file: %s" % path in result.output
    assert "not found" not in result.output
    assert "bass: songsterr, ug-bass" in result.output
    assert "guitar: ug-tab" in result.output


def test_config_command_with_partial_file_shows_defaults(tmp_path):
    path = write_config(tmp_path, '[bass]\norder = ["songsterr"]\n')
    result = run_config(tmp_path, ["--config", str(path)])
    assert "bass: songsterr" in result.output
    assert "guitar: ug-pro, ug-tab, songsterr" in result.output


def test_config_command_invalid_file(tmp_path):
    path = write_config(tmp_path, '[bass]\norder = ["ug-tab"]\n')
    result = run_config(tmp_path, ["--config", str(path)])
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_config_command_invalid_toml(tmp_path):
    path = write_config(tmp_path, "[bass\n")
    result = run_config(tmp_path, ["--config", str(path)])
    assert result.exit_code == 1
    assert "Error:" in result.output


# ------------------------------------------------------------- environment


def test_env_var_is_the_default_config_path_for_sort(tmp_path):
    cfg = write_config(tmp_path, '[bass]\norder = ["songsterr"]\n')
    result, factory, _ = run_sort(
        tmp_path, "bass", [], config=None, env={"TUNE_SORT_CONFIG": str(cfg)}
    )
    assert result.exit_code == 0, result.output
    assert factory.requested == [("bass", ["songsterr"])]


def test_config_flag_beats_env_var(tmp_path):
    env_cfg = tmp_path / "env.toml"
    env_cfg.write_text('[bass]\norder = ["songsterr"]\n', encoding="utf-8")
    flag_cfg = tmp_path / "flag.toml"
    flag_cfg.write_text('[bass]\norder = ["ug-bass"]\n', encoding="utf-8")
    _, factory, _ = run_sort(
        tmp_path, "bass", [], config=flag_cfg, env={"TUNE_SORT_CONFIG": str(env_cfg)}
    )
    assert factory.requested == [("bass", ["ug-bass"])]


def test_env_var_is_the_default_config_path_for_config_command(tmp_path):
    cfg = write_config(tmp_path, '[guitar]\norder = ["songsterr"]\n')
    result = run_config(tmp_path, [], env={"TUNE_SORT_CONFIG": str(cfg)})
    assert result.exit_code == 0, result.output
    assert "Config file: %s" % cfg in result.output
    assert "guitar: songsterr" in result.output
