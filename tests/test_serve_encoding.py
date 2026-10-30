"""`tune-sort serve` through the real CLI: odd bytes on stdin never break the line protocol."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from tests.conftest import FakeMusic
from tune_sort.cli import make_app

HELLO = b'{"id":2,"cmd":"hello","args":{}}\n'
HELLO_RESULT = {"id": 2, "result": {"protocol": 1, "instruments": ["bass", "guitar"]}}


def invoke_serve(tmp_path: Path, data: bytes) -> Any:
    app = make_app(lambda: FakeMusic(), lambda instrument, names: [])
    return CliRunner().invoke(
        app,
        ["serve", "--cache", str(tmp_path / "c.db"), "--config", str(tmp_path / "c.toml")],
        input=data,
    )


def test_serve_invalid_utf8_line_gets_bad_request(tmp_path: Path) -> None:
    result = invoke_serve(tmp_path, b"\xff\xfe not utf8\n" + HELLO)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["id"] is None
    assert first["error"]["kind"] == "bad_request"
    assert json.loads(lines[1]) == HELLO_RESULT


def test_serve_lone_surrogate_reply_is_one_line(tmp_path: Path) -> None:
    line = '{"id":1,"cmd":"\\ud800"}\n'.encode("ascii")
    result = invoke_serve(tmp_path, line + HELLO)
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["id"] == 1
    assert first["error"]["kind"] == "bad_request"
    assert json.loads(lines[1]) == HELLO_RESULT
