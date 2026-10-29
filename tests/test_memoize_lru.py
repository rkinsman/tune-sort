"""memoize keeps only the `maxsize` most recently used URLs."""
from __future__ import annotations

from typing import List

import pytest

from tune_sort.sources import FetchError, memoize


class Counting:
    def __init__(self):
        self.calls: List[str] = []

    def __call__(self, url):
        self.calls.append(url)
        return "body-" + url


def test_default_maxsize_keeps_many_urls():
    inner = Counting()
    fetch = memoize(inner)
    for i in range(64):
        fetch("u%d" % i)
    for i in range(64):
        fetch("u%d" % i)
    assert len(inner.calls) == 64


def test_default_maxsize_evicts_beyond_64():
    inner = Counting()
    fetch = memoize(inner)
    for i in range(65):
        fetch("u%d" % i)
    fetch("u0")
    assert inner.calls.count("u0") == 2
    fetch("u64")
    assert inner.calls.count("u64") == 1


def test_oldest_url_evicted_when_full():
    inner = Counting()
    fetch = memoize(inner, maxsize=2)
    fetch("a")
    fetch("b")
    fetch("c")  # evicts a
    assert inner.calls == ["a", "b", "c"]
    assert fetch("b") == "body-b"
    assert fetch("c") == "body-c"
    assert inner.calls == ["a", "b", "c"]
    assert fetch("a") == "body-a"
    assert inner.calls == ["a", "b", "c", "a"]


def test_hit_counts_as_use():
    inner = Counting()
    fetch = memoize(inner, maxsize=2)
    fetch("a")
    fetch("b")
    fetch("a")  # a is now most recent; b is oldest
    fetch("c")  # evicts b
    assert inner.calls == ["a", "b", "c"]
    fetch("a")
    assert inner.calls == ["a", "b", "c"]
    fetch("b")
    assert inner.calls == ["a", "b", "c", "b"]


def test_refetched_url_is_returned_correctly():
    inner = Counting()
    fetch = memoize(inner, maxsize=1)
    assert fetch("a") == "body-a"
    assert fetch("b") == "body-b"
    assert fetch("a") == "body-a"
    assert inner.calls == ["a", "b", "a"]


def test_maxsize_one_caches_the_latest_only():
    inner = Counting()
    fetch = memoize(inner, maxsize=1)
    fetch("a")
    fetch("a")
    assert inner.calls == ["a"]


def test_errors_do_not_occupy_slots_or_evict():
    class Flaky:
        def __init__(self):
            self.calls: List[str] = []

        def __call__(self, url):
            self.calls.append(url)
            if url.startswith("bad"):
                raise FetchError("down")
            return "body-" + url

    inner = Flaky()
    fetch = memoize(inner, maxsize=2)
    fetch("a")
    fetch("b")
    for _ in range(3):
        with pytest.raises(FetchError):
            fetch("bad")
    fetch("a")
    fetch("b")
    assert inner.calls == ["a", "b", "bad", "bad", "bad"]
