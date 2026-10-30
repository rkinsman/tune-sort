"""tune_sort.serve: the `sort` and `cancel` commands, events, busy and end-of-input."""
from __future__ import annotations

import io
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeMusic, FakeSource, make_match, make_track
from tune_sort.cache import Cache
from tune_sort.cli import make_app
from tune_sort.serve import serve
from tune_sort.sources import SourceError
from tune_sort.tuning import Instrument

DASH = "–"
DROP_D = "Bass %s Drop D" % DASH
EB_STD = "Bass %s Eb Standard" % DASH
BASS_DEFAULT = ["ug-pro", "ug-bass", "songsterr"]

A = make_track("A", "Tool", "Schism")
B = make_track("B", "Opeth", "Deliverance")
C = make_track("C", "Rush", "YYZ")
U = make_track("U", "Nobody", "Nothing")

ANSWERS = {
    ("Tool", "Schism"): make_match("D A D G"),
    ("Opeth", "Deliverance"): make_match("D# G# C# F#"),
    ("Rush", "YYZ"): make_match("D A D G"),
}

Msg = Dict[str, Any]


def tj(t: Any) -> Dict[str, str]:
    return {"artist": t.artist, "title": t.name, "persistent_id": t.persistent_id}


def req(id: Any, cmd: str, /, **args: Any) -> Dict[str, Any]:
    return {"id": id, "cmd": cmd, "args": args}


class Sink(io.StringIO):
    """Collects each write as one queued message."""

    def __init__(self) -> None:
        super().__init__()
        self.q: queue.Queue[str] = queue.Queue()

    def write(self, s: str) -> int:
        self.q.put(s)
        return len(s)

    def flush(self) -> None:
        pass


class BlockingSource(FakeSource):
    """Every lookup signals `entered`, then waits for `release`."""

    def __init__(self, entered: threading.Event, release: threading.Event, **kw: Any) -> None:
        super().__init__("blocking", **kw)
        self.entered = entered
        self.release = release

    def lookup(self, artist: str, title: str) -> Any:
        self.entered.set()
        self.release.wait(timeout=5)
        return super().lookup(artist, title)


class Factory:
    def __init__(self, sources: Optional[List[Any]] = None) -> None:
        self.calls: List[Tuple[str, List[str]]] = []
        self.sources = sources if sources is not None else [FakeSource("s", ANSWERS)]

    def __call__(self, instrument: str, names: Any) -> Any:
        self.calls.append((instrument, list(names)))
        return self.sources


class Session:
    def __init__(
        self,
        tmp_path: Path,
        music: FakeMusic,
        factory: Any,
        config_path: Optional[Path] = None,
    ) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.sink = Sink()
        self.raw: List[str] = []
        self.pending: List[Msg] = []
        self.errors: List[BaseException] = []
        r, w = os.pipe()
        self.stdin = os.fdopen(r, "r", encoding="utf-8")
        self.writer = os.fdopen(w, "w", encoding="utf-8")
        self.writer_closed = False
        cfg = config_path if config_path is not None else tmp_path / "config.toml"

        def open_cache(i: Instrument) -> Cache:
            return Cache(tmp_path / "t.db", i)

        def target() -> None:
            try:
                serve(self.stdin, self.sink, lambda: music, factory, open_cache, cfg)
            except BaseException as e:  # noqa: BLE001
                self.errors.append(e)

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def send(self, request: Any) -> None:
        text = request if isinstance(request, str) else json.dumps(request)
        self.writer.write(text + "\n")
        self.writer.flush()

    def close_input(self) -> None:
        if not self.writer_closed:
            self.writer_closed = True
            self.writer.close()

    def take(self, pred: Callable[[Msg], bool]) -> Msg:
        for i, m in enumerate(self.pending):
            if pred(m):
                return self.pending.pop(i)
        while True:
            line = self.sink.q.get(timeout=5)
            assert line.endswith("\n") and line.count("\n") == 1, repr(line)
            self.raw.append(line)
            parsed: Msg = json.loads(line)
            if pred(parsed):
                return parsed
            self.pending.append(parsed)

    def until_final(self, id: int) -> List[Msg]:
        out: List[Msg] = []
        while True:
            m = self.take(lambda m: m.get("id") == id)
            out.append(m)
            if "result" in m or "error" in m:
                return out

    def reply(self, id: int) -> Msg:
        return self.take(lambda m: m.get("id") == id)

    def finish(self) -> None:
        self.release.set()
        self.close_input()
        self.thread.join(5)
        assert not self.thread.is_alive()
        assert self.errors == []


@pytest.fixture
def make_session(tmp_path: Path) -> Iterator[Callable[..., Session]]:
    sessions: List[Session] = []

    def make(
        music: Optional[FakeMusic] = None,
        factory: Any = None,
        config_path: Optional[Path] = None,
    ) -> Session:
        s = Session(
            tmp_path,
            music if music is not None else FakeMusic({"P": [A, B, C]}),
            factory if factory is not None else Factory(),
            config_path,
        )
        sessions.append(s)
        return s

    yield make
    for s in sessions:
        s.release.set()
        s.close_input()
        s.thread.join(5)
        s.stdin.close()
    for s in sessions:
        assert not s.thread.is_alive()


def sort_req(id: int = 1, **over: Any) -> Dict[str, Any]:
    args: Dict[str, Any] = {"instrument": "bass", "playlist": "P"}
    args.update(over)
    return {"id": id, "cmd": "sort", "args": args}


def blocked_session(
    make_session: Callable[..., Session], music: Optional[FakeMusic] = None
) -> Session:
    entered = threading.Event()
    release = threading.Event()
    factory = Factory([BlockingSource(entered, release, answers=ANSWERS)])
    s = make_session(music=music, factory=factory)
    s.entered, s.release = entered, release
    return s


# ------------------------------------------------------------------ dry run


def test_sort_dry_run_events_then_report(make_session):
    music = FakeMusic({"P": [A, B, C]})
    s = make_session(music=music)
    s.send(sort_req(1, dry_run=True))
    msgs = s.until_final(1)
    events = [(m["event"], m["data"]) for m in msgs[:-1]]
    assert [e for e, _ in events] == ["start", "done"] * 3
    starts = [d for e, d in events if e == "start"]
    assert starts == [
        {"i": 1, "total": 3, "artist": "Tool", "title": "Schism"},
        {"i": 2, "total": 3, "artist": "Opeth", "title": "Deliverance"},
        {"i": 3, "total": 3, "artist": "Rush", "title": "YYZ"},
    ]
    dones = [d for e, d in events if e == "done"]
    assert [(d["artist"], d["title"], d["status"]) for d in dones] == [
        ("Tool", "Schism", "added"),
        ("Opeth", "Deliverance", "added"),
        ("Rush", "YYZ", "added"),
    ]
    report = msgs[-1]["result"]
    assert report["cancelled"] is False
    assert report["added"] == {DROP_D: [tj(A), tj(C)], EB_STD: [tj(B)]}
    assert report["review"] == []
    assert report["lookup_failed"] == []
    assert report["add_errors"] == []
    assert music.add_calls == []
    assert list(music.playlists) == ["P"]
    s.finish()


def test_sort_real_run_changes_music(make_session):
    music = FakeMusic({"P": [A, B]})
    s = make_session(music=music)
    s.send(sort_req(1))
    report = s.until_final(1)[-1]["result"]
    assert report["created_playlists"] == [DROP_D, EB_STD]
    assert music.playlists[DROP_D] == [A]
    assert music.playlists[EB_STD] == [B]
    s.finish()


# ------------------------------------------------------------------ statuses


def test_sort_done_statuses(make_session):
    src = FakeSource("s", {**ANSWERS, ("Opeth", "Deliverance"): SourceError("down")})
    music = FakeMusic({"P": [A, B, U], DROP_D: []})
    s = make_session(music=music, factory=Factory([src]))
    s.send(sort_req(1))
    msgs = s.until_final(1)
    dones = {m["data"]["title"]: m["data"] for m in msgs if m.get("event") == "done"}
    assert dones["Schism"]["status"] == "added"
    assert dones["Schism"]["playlist"] == DROP_D
    assert dones["Schism"]["source"] == "ug-bass"
    assert dones["Schism"]["tuning"]["notes"] == "D A D G"
    assert dones["Schism"]["tuning"]["name"] == "Drop D"
    assert dones["Deliverance"]["status"] == "lookup_failed"
    assert dones["Nothing"]["status"] == "review"
    report = msgs[-1]["result"]
    assert report["added"] == {DROP_D: [tj(A)]}
    assert report["lookup_failed"] == [tj(B)]
    assert report["review"] == [tj(U)]
    s.finish()


def test_sort_done_already_present(make_session):
    music = FakeMusic({"P": [A], DROP_D: [A]})
    s = make_session(music=music)
    s.send(sort_req(1))
    msgs = s.until_final(1)
    done = [m for m in msgs if m.get("event") == "done"][0]["data"]
    assert done["status"] == "already_present"
    assert done["playlist"] == DROP_D
    assert msgs[-1]["result"]["already_present"] == {DROP_D: [tj(A)]}
    s.finish()


def test_sort_done_add_error(make_session):
    music = FakeMusic({"P": [A]}, fail_add={"A": "boom"})
    s = make_session(music=music)
    s.send(sort_req(1))
    msgs = s.until_final(1)
    done = [m for m in msgs if m.get("event") == "done"][0]["data"]
    assert done["status"] == "add_error"
    assert done["error"] == "boom"
    errs = msgs[-1]["result"]["add_errors"]
    assert errs == [{"track": tj(A), "playlist": DROP_D, "error": "boom"}]
    s.finish()


# ------------------------------------------------------------------ args


def test_sort_order_and_source_args(make_session):
    f = Factory()
    s = make_session(factory=f)
    s.send(sort_req(1, dry_run=True, order=["songsterr", "ug-bass", "ug-pro"], source="ug"))
    s.until_final(1)
    assert f.calls == [("bass", ["ug-bass", "ug-pro"])]
    s.finish()


def test_sort_source_songsterr_default_order(make_session):
    f = Factory()
    s = make_session(factory=f)
    s.send(sort_req(1, dry_run=True, source="songsterr"))
    s.until_final(1)
    assert f.calls == [("bass", ["songsterr"])]
    s.finish()


def test_sort_uses_saved_order_by_default(make_session, tmp_path):
    cfg = tmp_path / "saved.toml"
    cfg.write_text('[bass]\norder = ["songsterr", "ug-bass"]\n', encoding="utf-8")
    f = Factory()
    s = make_session(factory=f, config_path=cfg)
    s.send(sort_req(1, dry_run=True))
    s.until_final(1)
    assert f.calls == [("bass", ["songsterr", "ug-bass"])]
    s.finish()


def test_sort_default_order_without_config(make_session):
    f = Factory()
    s = make_session(factory=f)
    s.send(sort_req(1, dry_run=True))
    s.until_final(1)
    assert f.calls == [("bass", BASS_DEFAULT)]
    s.finish()


# ------------------------------------------------------------------ errors


def test_sort_bad_order_config_error(make_session):
    music = FakeMusic({"P": [A]})
    s = make_session(music=music)
    s.send(sort_req(1, order=["ug-tab"]))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "config"
    assert m["error"]["message"]
    s.send(req(2, "hello"))
    assert "result" in s.reply(2)
    assert music.add_calls == []
    s.finish()


def test_sort_bad_source_bad_request(make_session):
    music = FakeMusic({"P": [A]})
    s = make_session(music=music)
    s.send(sort_req(1, source="bogus"))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "bad_request"
    assert music.add_calls == []
    s.finish()


def test_sort_no_sources_left_config_error(make_session):
    music = FakeMusic({"P": [A]})
    s = make_session(music=music)
    s.send(sort_req(1, order=["songsterr"], source="ug"))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "config"
    assert "no sources left after --source" in m["error"]["message"]
    assert music.add_calls == []
    s.finish()


@pytest.mark.parametrize(
    "over", [{"dry_run": "yes"}, {"recheck": 1}, {"dry_run": 0}, {"recheck": "true"}]
)
def test_sort_wrong_typed_flags_bad_request(make_session, over):
    s = make_session()
    s.send(sort_req(1, **over))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "bad_request"
    s.finish()


def test_sort_missing_playlist_arg_bad_request(make_session):
    s = make_session()
    s.send(req(1, "sort", instrument="bass"))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "bad_request"
    s.finish()


def test_sort_empty_playlist_result_no_events(make_session):
    s = make_session(music=FakeMusic({"P": []}))
    s.send(sort_req(1))
    msgs = s.until_final(1)
    assert len(msgs) == 1
    report = msgs[0]["result"]
    assert report["cancelled"] is False
    assert report["added"] == {}
    assert report["review"] == []
    assert report["lookup_failed"] == []
    s.finish()


def test_sort_missing_playlist_music_error(make_session):
    s = make_session()
    s.send(sort_req(1, playlist="Nope"))
    (m,) = s.until_final(1)
    assert m["error"]["kind"] == "music"
    assert "Nope" in m["error"]["message"]
    s.send(req(2, "hello"))
    assert "result" in s.reply(2)
    s.finish()


# ------------------------------------------------------------------ cancel


def test_cancel_mid_sort(make_session):
    music = FakeMusic({"P": [A, B, C]})
    s = blocked_session(make_session, music)
    s.send(sort_req(1))
    assert s.entered.wait(5)
    s.send(req(2, "cancel", id=1))
    assert s.reply(2) == {"id": 2, "result": {}}
    s.release.set()
    msgs = s.until_final(1)
    assert [m.get("event") for m in msgs[:-1]] == ["start", "done"]
    assert msgs[0]["data"]["i"] == 1
    assert msgs[1]["data"]["status"] == "added"
    report = msgs[-1]["result"]
    assert report["cancelled"] is True
    assert report["added"] == {DROP_D: [tj(A)]}
    assert music.playlists[DROP_D] == [A]
    assert B not in music.playlists.get(EB_STD, [])
    s.finish()


def test_cancel_unknown_id_bad_request_and_sort_unaffected(make_session):
    s = blocked_session(make_session)
    s.send(sort_req(1, dry_run=True))
    assert s.entered.wait(5)
    s.send(req(2, "cancel", id=99))
    assert s.reply(2)["error"]["kind"] == "bad_request"
    s.release.set()
    msgs = s.until_final(1)
    assert [m.get("event") for m in msgs[:-1]] == ["start", "done"] * 3
    assert msgs[-1]["result"]["cancelled"] is False
    s.finish()


def test_cancel_with_nothing_running_bad_request(make_session):
    s = make_session()
    s.send(req(1, "cancel", id=5))
    assert s.reply(1)["error"]["kind"] == "bad_request"
    s.finish()


def test_cancel_after_finish_bad_request(make_session):
    s = make_session()
    s.send(sort_req(1, dry_run=True))
    assert "result" in s.until_final(1)[-1]
    s.send(req(2, "cancel", id=1))
    assert s.reply(2)["error"]["kind"] == "bad_request"
    s.finish()


def test_cancel_missing_or_non_int_id_bad_request(make_session):
    s = blocked_session(make_session)
    s.send(sort_req(1, dry_run=True))
    assert s.entered.wait(5)
    s.send(req(2, "cancel"))
    s.send(req(3, "cancel", id="1"))
    assert s.reply(2)["error"]["kind"] == "bad_request"
    assert s.reply(3)["error"]["kind"] == "bad_request"
    s.release.set()
    msgs = s.until_final(1)
    assert msgs[-1]["result"]["cancelled"] is False
    assert len([m for m in msgs if m.get("event") == "done"]) == 3
    s.finish()


# ------------------------------------------------------------------ busy / EOF


def test_busy_during_sort(make_session):
    s = blocked_session(make_session)
    s.send(sort_req(1, dry_run=True))
    assert s.entered.wait(5)
    s.send(req(2, "hello"))
    s.send(sort_req(3, dry_run=True))
    for id in (2, 3):
        m = s.reply(id)
        assert m["error"]["kind"] == "busy"
        assert m["error"]["message"]
    s.release.set()
    msgs = s.until_final(1)
    assert [m.get("event") for m in msgs[:-1]] == ["start", "done"] * 3
    assert msgs[-1]["result"]["cancelled"] is False
    s.send(req(4, "hello"))
    assert s.reply(4)["result"]["protocol"] == 1
    s.finish()


def test_pipelined_non_sort_requests_never_busy(make_session):
    s = make_session()
    for i in range(1, 6):
        s.send(req(i, "hello"))
    for i in range(1, 6):
        assert "result" in s.reply(i)
    s.finish()


def test_eof_during_sort_cancels(make_session):
    music = FakeMusic({"P": [A, B, C]})
    s = blocked_session(make_session, music)
    s.send(sort_req(1))
    assert s.entered.wait(5)
    s.close_input()
    # Give the reader thread a moment to see end of input before the track finishes.
    threading.Event().wait(0.3)
    s.release.set()
    msgs = s.until_final(1)
    assert msgs[-1]["result"]["cancelled"] is True
    assert [m.get("event") for m in msgs[:-1]] == ["start", "done"]
    s.thread.join(5)
    assert not s.thread.is_alive()
    assert s.errors == []


# ------------------------------------------------------------------ reuse / unicode


def test_sources_reused_across_sorts(make_session):
    f = Factory()
    s = make_session(factory=f)
    s.send(sort_req(1, dry_run=True))
    s.until_final(1)
    s.send(sort_req(2, dry_run=True))
    s.until_final(2)
    assert f.calls == [("bass", BASS_DEFAULT)]
    s.send(sort_req(3, dry_run=True, order=["songsterr"]))
    s.until_final(3)
    assert f.calls == [("bass", BASS_DEFAULT), ("bass", ["songsterr"])]
    s.finish()


def test_unicode_in_events(make_session):
    track = make_track("S", "Sigur Rós", "Hoppípolla")
    src = FakeSource("s", {("Sigur Rós", "Hoppípolla"): make_match("D A D G")})
    s = make_session(music=FakeMusic({"P": [track]}), factory=Factory([src]))
    s.send(sort_req(1, dry_run=True))
    msgs = s.until_final(1)
    assert msgs[0]["data"]["artist"] == "Sigur Rós"
    raw = "".join(s.raw)
    assert "Sigur Rós" in raw
    assert "Hoppípolla" in raw
    assert "\\u" not in raw
    s.finish()


# ------------------------------------------------------------------ CLI


def test_cli_serve_hello(tmp_path):
    app = make_app(lambda: FakeMusic(), lambda instrument, names: [])
    result = CliRunner().invoke(
        app,
        ["serve", "--cache", str(tmp_path / "c.db"), "--config", str(tmp_path / "c.toml")],
        input='{"id":1,"cmd":"hello","args":{}}\n',
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {
        "id": 1,
        "result": {"protocol": 1, "instruments": ["bass", "guitar"]},
    }
