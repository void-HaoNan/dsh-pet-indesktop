"""口型同步：有声音继续播，停顿把说话动画暂停在那一帧。"""

from __future__ import annotations

import json

from pet import mouth_sync


class _Movie:
    def __init__(self):
        self.calls = []

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")


class _Win:
    def __init__(self):
        self.movie = _Movie()


def test_read_mouth(tmp_path):
    path = tmp_path / "mouth.json"
    path.write_text(json.dumps({"open": 1, "talking": True}), encoding="utf-8")
    obj = mouth_sync.read_mouth(str(path))
    assert obj and obj["open"] == 1


def test_read_mouth_missing_returns_none(tmp_path):
    assert mouth_sync.read_mouth(str(tmp_path / "nope.json")) is None


def test_apply_mouth_pauses_and_resumes():
    win = _Win()
    assert mouth_sync.apply_mouth(win, False) is True
    assert win.movie.calls == ["pause"]
    assert mouth_sync.apply_mouth(win, True) is True
    assert win.movie.calls == ["pause", "resume"]


def test_apply_mouth_without_movie_is_noop():
    class _Empty:
        movie = None

    assert mouth_sync.apply_mouth(_Empty(), False) is False
