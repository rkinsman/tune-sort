"""tune_sort.serve: the JSON-lines protocol (non-sort commands)."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List

from tests.conftest import FakeMusic, T, make_match, make_track
from tune_sort.cache import Cache, Entry
from tune_sort.serve import PROTOCOL_VERSION, serve
from tune_sort.tuning import Instrument

DASH = "–"
BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]
GUITAR_DEFAULT = ["ug-pro", "ug-tab", "songsterr"]

DROP_D_JSON = {"name": "Drop D", "playlist_name": "Bass %s Drop D" % DASH, "notes": "D A D G"}
GUITAR_DROP_D_JSON = {
    "name": "Drop D",
    "playlist_name": "Guitar %s Drop D" % DASH,
    "notes": "D A D G B E",
}

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")

OPETH_MATCH = make_match("D A D G", artist="Opeth", title="Deliverance")

Request = Dict[str, Any] | str


class BoomMusic(FakeMusic):
    def list_playlists(self) -> List[str]:
        raise RuntimeError("kaboom")


def req(id: int, cmd: str, **args: Any) -> Dict[str, Any]:
    return {"id": id, "cmd": cmd, "args": args}


def run_raw(
    tmp_path: Path,
    requests: List[Request],
    music: FakeMusic | None = None,
    config_path: Path | None = None,
) -> str:
    lines = [r if isinstance(r, str) else json.dumps(r) for r in requests]
    stdin = io.StringIO("".join(line + "\n" for line in lines))
    stdout = io.StringIO()
    the_music = music if music is not None else FakeMusic({"P": [A, B, C]})
    serve(
        stdin,
        stdout,
        lambda: the_music,
        lambda instrument, names: [],
        lambda instrument: Cache(tmp_path / "t.db", instrument),
        config_path if config_path is not None else tmp_path / "config.toml",
    )
    return stdout.getvalue()


def run(tmp_path: Path, requests: List[Request], **kw: Any) -> List[Dict[str, Any]]:
    out = run_raw(tmp_path, requests, **kw)
    return [json.loads(line) for line in out.splitlines()]


def one(tmp_path: Path, request: Request, **kw: Any) -> Dict[str, Any]:
    (reply,) = run(tmp_path, [request], **kw)
    return reply


def result(tmp_path: Path, request: Request, **kw: Any) -> Any:
    reply = one(tmp_path, request, **kw)
    assert "error" not in reply, reply
    return reply["result"]


def seed(tmp_path: Path, instrument: Instrument = "bass") -> Cache:
    return Cache(tmp_path / "t.db", instrument)


# ------------------------------------------------------------------- basics


def test_protocol_version_constant():
    assert PROTOCOL_VERSION == 1


def test_hello(tmp_path):
    assert one(tmp_path, req(1, "hello")) == {
        "id": 1,
        "result": {"protocol": 1, "instruments": ["bass", "guitar"]},
    }


def test_hello_without_args_key(tmp_path):
    reply = one(tmp_path, {"id": 2, "cmd": "hello"})
    assert reply == {"id": 2, "result": {"protocol": 1, "instruments": ["bass", "guitar"]}}


def test_replies_carry_request_ids_in_order(tmp_path):
    replies = run(tmp_path, [req(7, "hello"), req(3, "playlists"), req(42, "hello")])
    assert [r["id"] for r in replies] == [7, 3, 42]


def test_returns_at_eof(tmp_path):
    assert run_raw(tmp_path, []) == ""


def test_replies_one_line_each_utf8(tmp_path):
    music = FakeMusic({"Sigur Rós": [make_track("S", "Sigur Rós", "Hoppípolla")]})
    out = run_raw(
        tmp_path,
        [req(1, "playlists"), req(2, "tracks", instrument="bass", playlist="Sigur Rós")],
        music=music,
    )
    assert "Sigur Rós" in out
    assert "\\u" not in out
    lines = out.splitlines()
    assert len(lines) == 2
    assert out.endswith("\n")
    assert json.loads(lines[0])["result"] == ["Sigur Rós"]
    assert json.loads(lines[1])["result"][0]["artist"] == "Sigur Rós"


# ---------------------------------------------------------------- playlists / tracks


def test_playlists(tmp_path):
    music = FakeMusic({"One": [], "Two": [A]})
    assert result(tmp_path, req(1, "playlists"), music=music) == ["One", "Two"]


def test_tracks_with_states(tmp_path):
    c = seed(tmp_path)
    c.put("Tool", "Schism", Entry(T("D A D G"), "ug-bass", True))
    c.add_review("Opeth", "Deliverance", [OPETH_MATCH])
    c.close()
    got = result(tmp_path, req(1, "tracks", instrument="bass", playlist="P"))
    assert got == [
        {
            "artist": "Tool",
            "title": "Schism",
            "persistent_id": "A",
            "state": "cached",
            "tuning": DROP_D_JSON,
            "source": "ug-bass",
            "confirmed": True,
        },
        {
            "artist": "Opeth",
            "title": "Deliverance",
            "persistent_id": "B",
            "state": "review",
            "candidates": [
                {
                    "tuning": DROP_D_JSON,
                    "source": "ug-bass",
                    "url": "https://example.test/ug-bass",
                    "matched_artist": "Opeth",
                    "matched_title": "Deliverance",
                    "exact": True,
                }
            ],
        },
        {"artist": "Rush", "title": "YYZ", "persistent_id": "C", "state": "unknown"},
    ]


def test_tracks_uses_the_instruments_cache(tmp_path):
    g = seed(tmp_path, "guitar")
    g.put("Tool", "Schism", Entry(T("D A D G B E", "guitar"), "ug-pro", True))
    g.close()
    bass = result(tmp_path, req(1, "tracks", instrument="bass", playlist="P"))
    guitar = result(tmp_path, req(1, "tracks", instrument="guitar", playlist="P"))
    assert bass[0]["state"] == "unknown"
    assert guitar[0]["state"] == "cached"
    assert guitar[0]["tuning"] == GUITAR_DROP_D_JSON


# ------------------------------------------------------------- config / set_order


def test_config_defaults_when_no_file(tmp_path):
    path = tmp_path / "config.toml"
    assert result(tmp_path, req(1, "config"), config_path=path) == {
        "path": str(path),
        "exists": False,
        "order": {"bass": BASS_DEFAULT, "guitar": GUITAR_DEFAULT},
        "sources": {"bass": BASS_DEFAULT, "guitar": GUITAR_DEFAULT},
    }


def test_config_reads_file(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[bass]\norder = ["songsterr", "ug-bass"]\n', encoding="utf-8")
    got = result(tmp_path, req(1, "config"), config_path=path)
    assert got["exists"] is True
    assert got["path"] == str(path)
    assert got["order"] == {"bass": ["songsterr", "ug-bass"], "guitar": GUITAR_DEFAULT}


def test_config_reports_sources(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[bass]\norder = ["songsterr"]\n', encoding="utf-8")
    got = result(tmp_path, req(1, "config"), config_path=path)
    assert got["sources"] == {"bass": BASS_DEFAULT, "guitar": GUITAR_DEFAULT}


def test_config_invalid_file_is_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[bass]\norder = ["x"]\n', encoding="utf-8")
    reply = one(tmp_path, req(5, "config"), config_path=path)
    assert reply["id"] == 5
    assert reply["error"]["kind"] == "config"
    assert reply["error"]["message"].startswith(str(path))
    assert "unknown source 'x' for bass" in reply["error"]["message"]


def test_set_order_returns_new_order_and_persists(tmp_path):
    path = tmp_path / "config.toml"
    replies = run(
        tmp_path,
        [
            req(1, "set_order", instrument="bass", order=["songsterr", "ug-bass"]),
            req(2, "config"),
        ],
        config_path=path,
    )
    assert replies[0] == {"id": 1, "result": ["songsterr", "ug-bass"]}
    assert replies[1]["result"]["order"]["bass"] == ["songsterr", "ug-bass"]
    assert replies[1]["result"]["order"]["guitar"] == GUITAR_DEFAULT
    assert replies[1]["result"]["exists"] is True


def test_set_order_null_resets_to_default(tmp_path):
    path = tmp_path / "config.toml"
    replies = run(
        tmp_path,
        [
            req(1, "set_order", instrument="guitar", order=["songsterr"]),
            req(2, "set_order", instrument="guitar", order=None),
        ],
        config_path=path,
    )
    assert replies[0]["result"] == ["songsterr"]
    assert replies[1] == {"id": 2, "result": GUITAR_DEFAULT}


def test_set_order_invalid_is_config_error(tmp_path):
    path = tmp_path / "config.toml"
    replies = run(
        tmp_path,
        [req(1, "set_order", instrument="bass", order=["ug-tab"]), req(2, "config")],
        config_path=path,
    )
    assert replies[0]["id"] == 1
    assert replies[0]["error"]["kind"] == "config"
    assert replies[0]["error"]["message"]
    assert replies[1]["result"]["order"]["bass"] == BASS_DEFAULT


# --------------------------------------------------------------- review_list


def test_review_list(tmp_path):
    c = seed(tmp_path)
    c.add_review("Opeth", "Deliverance", [OPETH_MATCH])
    c.close()
    got = result(tmp_path, req(1, "review_list", instrument="bass"))
    assert got == [
        {
            "artist": "Opeth",
            "title": "Deliverance",
            "candidates": [
                {
                    "tuning": DROP_D_JSON,
                    "source": "ug-bass",
                    "url": "https://example.test/ug-bass",
                    "matched_artist": "Opeth",
                    "matched_title": "Deliverance",
                    "exact": True,
                }
            ],
        }
    ]


def test_review_list_empty(tmp_path):
    assert result(tmp_path, req(1, "review_list", instrument="bass")) == []


def test_review_list_is_per_instrument(tmp_path):
    c = seed(tmp_path)
    c.add_review("Opeth", "Deliverance", [])
    c.close()
    assert result(tmp_path, req(1, "review_list", instrument="guitar")) == []


# ------------------------------------------------------------------ describe


def test_describe(tmp_path):
    got = result(tmp_path, req(1, "describe", instrument="bass", tuning="Drop D"))
    assert got == {"tuning": DROP_D_JSON}


def test_describe_guitar(tmp_path):
    got = result(tmp_path, req(1, "describe", instrument="guitar", tuning="Drop D"))
    assert got == {"tuning": GUITAR_DROP_D_JSON}


def test_describe_bad_tuning_message_matches_cli(tmp_path):
    reply = one(tmp_path, req(4, "describe", instrument="bass", tuning="xyz"))
    assert reply["id"] == 4
    assert reply["error"]["kind"] == "bad_tuning"
    msg = reply["error"]["message"]
    assert msg.startswith("tuning not understood: 'xyz' (")
    assert msg.endswith(")")


# ------------------------------------------------- set / entries / delete


def test_set_returns_stored_entry(tmp_path):
    got = result(
        tmp_path, req(1, "set", instrument="bass", artist="Tool", title="Schism", tuning="Drop D")
    )
    assert got["artist"] == "Tool"
    assert got["title"] == "Schism"
    assert got["tuning"] == DROP_D_JSON
    assert got["confirmed"] is True
    assert set(got) == {"artist", "title", "tuning", "source", "confirmed"}


def test_set_bad_tuning(tmp_path):
    reply = one(
        tmp_path, req(1, "set", instrument="bass", artist="Tool", title="Schism", tuning="xyz")
    )
    assert reply["error"]["kind"] == "bad_tuning"
    assert reply["error"]["message"].startswith("tuning not understood: 'xyz' (")


def test_entries_empty(tmp_path):
    assert result(tmp_path, req(1, "entries", instrument="bass")) == []


def test_set_then_entries_and_tracks_show_it(tmp_path):
    replies = run(
        tmp_path,
        [
            req(1, "set", instrument="bass", artist="Tool", title="Schism", tuning="Drop D"),
            req(2, "entries", instrument="bass"),
            req(3, "tracks", instrument="bass", playlist="P"),
        ],
    )
    stored = replies[0]["result"]
    assert replies[1]["result"] == [stored]
    assert stored["tuning"] == DROP_D_JSON
    tracks = replies[2]["result"]
    assert tracks[0]["state"] == "cached"
    assert tracks[0]["tuning"] == DROP_D_JSON
    assert tracks[0]["source"] == stored["source"]
    assert tracks[0]["confirmed"] is True
    assert tracks[1]["state"] == "unknown"


def test_entries_sorted_by_artist_then_title(tmp_path):
    c = seed(tmp_path)
    e = Entry(T("D A D G"), "manual", True)
    c.put("tool", "Parabola", e)
    c.put("abba", "Waterloo", e)
    c.put("Beatles", "Help", e)
    c.close()
    got = result(tmp_path, req(1, "entries", instrument="bass"))
    assert [(x["artist"], x["title"]) for x in got] == [
        ("abba", "Waterloo"),
        ("Beatles", "Help"),
        ("tool", "Parabola"),
    ]
    assert got[0] == {
        "artist": "abba",
        "title": "Waterloo",
        "tuning": DROP_D_JSON,
        "source": "manual",
        "confirmed": True,
    }


def test_entries_per_instrument(tmp_path):
    c = seed(tmp_path)
    c.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    c.close()
    assert result(tmp_path, req(1, "entries", instrument="guitar")) == []


def test_set_clears_review(tmp_path):
    c = seed(tmp_path)
    c.add_review("Opeth", "Deliverance", [OPETH_MATCH])
    c.close()
    replies = run(
        tmp_path,
        [
            req(1, "review_list", instrument="bass"),
            req(2, "set", instrument="bass", artist="Opeth", title="Deliverance", tuning="Drop D"),
            req(3, "review_list", instrument="bass"),
        ],
    )
    assert len(replies[0]["result"]) == 1
    assert "error" not in replies[1]
    assert replies[2]["result"] == []


def test_delete_returns_empty_object(tmp_path):
    c = seed(tmp_path)
    c.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    c.close()
    reply = one(tmp_path, req(1, "delete", instrument="bass", artist="Tool", title="Schism"))
    assert reply == {"id": 1, "result": {}}


def test_delete_then_tracks_unknown(tmp_path):
    c = seed(tmp_path)
    c.put("Tool", "Schism", Entry(T("D A D G"), "manual", True))
    c.add_review("Opeth", "Deliverance", [])
    c.close()
    replies = run(
        tmp_path,
        [
            req(1, "delete", instrument="bass", artist="Tool", title="Schism"),
            req(2, "delete", instrument="bass", artist="Opeth", title="Deliverance"),
            req(3, "tracks", instrument="bass", playlist="P"),
            req(4, "entries", instrument="bass"),
            req(5, "review_list", instrument="bass"),
        ],
    )
    assert replies[0]["result"] == {}
    assert replies[1]["result"] == {}
    assert [t["state"] for t in replies[2]["result"]] == ["unknown", "unknown", "unknown"]
    assert replies[3]["result"] == []
    assert replies[4]["result"] == []


def test_delete_uncached_is_not_an_error(tmp_path):
    reply = one(tmp_path, req(1, "delete", instrument="bass", artist="Nobody", title="Nothing"))
    assert reply == {"id": 1, "result": {}}


# -------------------------------------------------------------------- errors


def test_unknown_cmd_bad_request(tmp_path):
    reply = one(tmp_path, req(9, "frobnicate"))
    assert reply["id"] == 9
    assert reply["error"]["kind"] == "bad_request"
    assert reply["error"]["message"]


def test_missing_arg_bad_request(tmp_path):
    reply = one(tmp_path, req(2, "tracks", instrument="bass"))
    assert reply["id"] == 2
    assert reply["error"]["kind"] == "bad_request"


def test_missing_args_object_bad_request(tmp_path):
    reply = one(tmp_path, {"id": 2, "cmd": "tracks"})
    assert reply["error"]["kind"] == "bad_request"


def test_wrong_typed_arg_bad_request(tmp_path):
    reply = one(tmp_path, req(2, "tracks", instrument="bass", playlist=5))
    assert reply["error"]["kind"] == "bad_request"


def test_wrong_typed_order_bad_request(tmp_path):
    reply = one(tmp_path, req(2, "set_order", instrument="bass", order="songsterr"))
    assert reply["error"]["kind"] == "bad_request"


def test_bad_instrument_bad_request(tmp_path):
    reply = one(tmp_path, req(3, "entries", instrument="banjo"))
    assert reply["id"] == 3
    assert reply["error"]["kind"] == "bad_request"


def test_unparseable_line_bad_request_id_null(tmp_path):
    reply = one(tmp_path, "this is not json")
    assert reply["id"] is None
    assert reply["error"]["kind"] == "bad_request"


def test_non_object_line_bad_request_id_null(tmp_path):
    reply = one(tmp_path, "[1, 2, 3]")
    assert reply["id"] is None
    assert reply["error"]["kind"] == "bad_request"


def test_missing_cmd_keeps_readable_id(tmp_path):
    reply = one(tmp_path, '{"id": 5}')
    assert reply["id"] == 5
    assert reply["error"]["kind"] == "bad_request"


def test_non_string_cmd_keeps_readable_id(tmp_path):
    reply = one(tmp_path, '{"id": 6, "cmd": 12}')
    assert reply["id"] == 6
    assert reply["error"]["kind"] == "bad_request"


def test_missing_id_bad_request_id_null(tmp_path):
    reply = one(tmp_path, '{"cmd": "hello"}')
    assert reply["id"] is None
    assert reply["error"]["kind"] == "bad_request"


def test_bad_line_does_not_stop_the_helper(tmp_path):
    replies = run(tmp_path, ["garbage", req(1, "hello")])
    assert replies[0]["error"]["kind"] == "bad_request"
    assert replies[1]["result"]["protocol"] == 1


def test_music_error_kind(tmp_path):
    reply = one(tmp_path, req(8, "tracks", instrument="bass", playlist="Nope"))
    assert reply["id"] == 8
    assert reply["error"]["kind"] == "music"
    assert "Nope" in reply["error"]["message"]


def test_internal_error_keeps_running(tmp_path):
    replies = run(
        tmp_path,
        [req(1, "playlists"), req(2, "hello")],
        music=BoomMusic({"P": []}),
    )
    assert replies[0]["id"] == 1
    assert replies[0]["error"]["kind"] == "internal"
    assert replies[1] == {
        "id": 2,
        "result": {"protocol": 1, "instruments": ["bass", "guitar"]},
    }
