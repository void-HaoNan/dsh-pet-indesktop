"""口型同步：按播放侧写出的 mouth.json 控制说话动画的张嘴/闭嘴。

聊天语音在播放时会按 PCM 能量写 ``mouth.json``：

    {"open": 1, "talking": true, "at": 1712345678.9}

``open=1`` 表示这一小段有声音（张嘴），``open=0`` 表示停顿（逗号、句间），
桌宠把当前说话动画暂停在那一帧当「闭嘴」用——不自造嘴型素材，也不改动画本身。

这里只放纯逻辑，方便单测；真正的窗口对象由 app.py 传进来。
"""

from __future__ import annotations

import json
import os

MOUTH_FILE = os.path.join(os.environ.get("APPDATA", ""), "dsh-pet-bubble", "mouth.json")


def read_mouth(path: str | None = None) -> dict | None:
    """读当前口型状态；文件不存在或读坏了返回 None。"""
    try:
        with open(path or MOUTH_FILE, "r", encoding="utf-8-sig") as handle:
            obj = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def apply_mouth(win, open_mouth: bool) -> bool:
    """有声音就继续播，没声音就把当前说话动画暂停（闭嘴）。

    返回是否真的动过播放状态，方便调用方只在状态变化时记日志。
    """
    movie = getattr(win, "movie", None)
    if movie is None:
        return False
    try:
        if open_mouth:
            movie.resume()
        else:
            movie.pause()
    except Exception:
        return False
    return True
