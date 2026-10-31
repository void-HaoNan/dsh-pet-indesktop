"""桌宠精简控制面板：只放和桌宠聊天相关的开关与状态。

设计边界（和上游保持一致）：
- 面板不碰直播/点歌/播放这些业务，只做「桌宠相关」的本地开关和进程状态；
- 语音回复、读麦克风、听电脑声音是通过本机 HTTP 接口交给外部服务执行的，
  地址写在配置文件里，服务不在就当不可用显示，不影响桌宠本体；
- 语音合成设置直接写桌宠自己的配置（voice_chime_* 一组键）。

面板入口：托盘菜单「控制面板」。
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import urllib.request

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

VOICE_CHOICES = (
    ("zh-CN-XiaoxiaoNeural", "晓晓（女）"),
    ("zh-CN-YunxiNeural", "云希（男）"),
    ("zh-CN-XiaoyiNeural", "晓伊（女）"),
    ("zh-CN-YunyangNeural", "云扬（男）"),
    ("zh-CN-liaoning-XiaobeiNeural", "晓北（东北）"),
)


def _probe(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


class PetControlPanel(QWidget):
    """小面板：重启桌宠、语音回复、读麦克风、听电脑声音、对话悬浮窗、服务状态、语音合成。"""

    _probed = Signal(object)

    def __init__(self, cfg, on_open_chat=None, on_restart=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._on_open_chat = on_open_chat
        self._on_restart = on_restart
        self._drag = None
        self._probed.connect(self._apply_status)

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(360)

        shell = QFrame(self)
        shell.setObjectName("panelShell")
        shell.setStyleSheet(
            """
            QFrame#panelShell { background: rgba(255,255,255,246); border-radius: 16px;
                                border: 1px solid rgba(0,0,0,20); }
            QLabel#title { font-size: 15px; color: #1d1d1f; font-weight: 600; }
            QLabel#row { font-size: 13px; color: #1d1d1f; }
            QLabel#hint { font-size: 11px; color: #9a9aa0; }
            QLabel#status { font-size: 12px; color: #6e6e73; }
            QPushButton#close { border: none; background: transparent; color: #8e8e93; font-size: 16px; }
            QPushButton#close:hover { color: #ff5f57; }
            QPushButton#action { border: 1px solid rgba(0,0,0,26); border-radius: 10px;
                                 background: rgba(255,255,255,228); padding: 4px 12px; font-size: 12px; }
            QPushButton#action:hover { background: #f2f2f7; }
            QCheckBox::indicator { width: 36px; height: 20px; border-radius: 10px; background: #e5e5ea; }
            QCheckBox::indicator:checked { background: #34c759; }
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(shell)
        body = QVBoxLayout(shell)
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("控制面板")
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("close")
        close.setFixedSize(24, 24)
        close.clicked.connect(self.hide)
        head.addWidget(close)
        body.addLayout(head)

        self._rows = {}
        for key, text, handler in (
            ("voice_reply", "语音回复", self._toggle_voice_reply),
            ("mic", "读麦克风", self._toggle_mic),
            ("desktop", "听电脑声音", self._toggle_desktop),
        ):
            row = QHBoxLayout()
            label = QLabel(text)
            label.setObjectName("row")
            row.addWidget(label)
            row.addStretch(1)
            box = QCheckBox()
            box.setFixedWidth(36)
            box.toggled.connect(handler)
            row.addWidget(box, 0, Qt.AlignVCenter)
            body.addLayout(row)
            self._rows[key] = box

        chat_row = QHBoxLayout()
        chat_label = QLabel("对话悬浮窗")
        chat_label.setObjectName("row")
        chat_row.addWidget(chat_label)
        chat_row.addStretch(1)
        open_chat = QPushButton("打开")
        open_chat.setObjectName("action")
        open_chat.clicked.connect(self._open_chat)
        chat_row.addWidget(open_chat)
        body.addLayout(chat_row)

        restart_row = QHBoxLayout()
        restart_label = QLabel("重启桌宠")
        restart_label.setObjectName("row")
        restart_row.addWidget(restart_label)
        restart_row.addStretch(1)
        restart = QPushButton("重启")
        restart.setObjectName("action")
        restart.clicked.connect(self._restart)
        restart_row.addWidget(restart)
        body.addLayout(restart_row)

        body.addWidget(self._divider())
        status_title = QLabel("服务状态")
        status_title.setObjectName("hint")
        body.addWidget(status_title)
        self._status_rows = {}
        for key, name, port in (("astrbot", "AstrBot", 6185), ("snowluma", "SnowLuma", 5099),
                                ("hub", "直播中台", 8897)):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet("color:#c7c7cc;font-size:10px;")
            name_label = QLabel(name)
            name_label.setObjectName("status")
            state = QLabel("检测中")
            state.setObjectName("status")
            row.addWidget(dot)
            row.addWidget(name_label)
            row.addStretch(1)
            row.addWidget(state)
            body.addLayout(row)
            self._status_rows[key] = (dot, state, port)

        body.addWidget(self._divider())
        tts_title = QLabel("语音合成")
        tts_title.setObjectName("hint")
        body.addWidget(tts_title)

        voice_row = QHBoxLayout()
        voice_label = QLabel("音色")
        voice_label.setObjectName("row")
        voice_row.addWidget(voice_label)
        self.voice_combo = QComboBox()
        for value, name in VOICE_CHOICES:
            self.voice_combo.addItem(name, value)
        self.voice_combo.setFixedWidth(190)
        self.voice_combo.currentIndexChanged.connect(self._voice_changed)
        voice_row.addStretch(1)
        voice_row.addWidget(self.voice_combo)
        body.addLayout(voice_row)

        self.rate_slider, rate_row = self._slider_row("语速", -50, 50, "voice_chime_rate", body)
        self.volume_slider, volume_row = self._slider_row("音量", 0, 100, "voice_chime_volume", body)

        self._load_state()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(3000)
        QTimer.singleShot(0, self._refresh_status)

    # ---------- 布局辅助 ----------
    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#e8e8ed;")
        return line

    def _slider_row(self, text: str, low: int, high: int, key: str, body: QVBoxLayout):
        row = QHBoxLayout()
        label = QLabel(text)
        label.setObjectName("row")
        label.setFixedWidth(40)
        row.addWidget(label)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(low, high)
        value = QLabel("")
        value.setObjectName("hint")
        value.setFixedWidth(36)
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider.valueChanged.connect(lambda v, lbl=value: lbl.setText(str(v)))
        slider.sliderReleased.connect(lambda s=slider, k=key: self._save_int(k, s.value()))
        row.addWidget(slider, 1)
        row.addWidget(value)
        body.addLayout(row)
        return slider, row

    # ---------- 状态 ----------
    def _load_state(self) -> None:
        value = str(self.cfg.get("voice_chime_voice", VOICE_CHOICES[0][0]))
        index = self.voice_combo.findData(value)
        if index >= 0:
            self.voice_combo.setCurrentIndex(index)
        for key, slider in (("voice_chime_rate", self.rate_slider),
                            ("voice_chime_volume", self.volume_slider)):
            try:
                slider.setValue(int(self.cfg.get(key, slider.value())))
            except (TypeError, ValueError):
                pass
        for key, box in self._rows.items():
            box.blockSignals(True)
            box.setChecked(self._flag(key))
            box.blockSignals(False)

    def _flag(self, key: str) -> bool:
        if key == "voice_reply":
            return bool(self.cfg.get("chat_reply_voice_enabled", False))
        return bool(self.cfg.get(f"panel_{key}", False))

    def _refresh_status(self) -> None:
        ports = {key: row[2] for key, row in self._status_rows.items()}

        def work():
            result = {key: _probe("127.0.0.1", port) for key, port in ports.items()}
            self._probed.emit(result)

        threading.Thread(target=work, daemon=True).start()

    def _apply_status(self, result) -> None:
        for key, (dot, state, _port) in self._status_rows.items():
            ok = bool(result.get(key))
            dot.setStyleSheet("color:#34c759;font-size:10px;" if ok
                              else "color:#ff3b30;font-size:10px;")
            state.setText("运行中" if ok else "未运行")

    # ---------- 开关 ----------
    def _post(self, path: str, payload: dict) -> None:
        base = str(self.cfg.get("panel_hub_url", "http://127.0.0.1:8897")).rstrip("/")

        def work():
            try:
                request = urllib.request.Request(
                    base + path, data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(request, timeout=8).read()
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _toggle_voice_reply(self, checked: bool) -> None:
        self.cfg.set("chat_reply_voice_enabled", bool(checked))
        self.cfg.save()
        self._post("/tts/power", {"on": bool(checked)})

    def _toggle_mic(self, checked: bool) -> None:
        self.cfg.set("panel_mic", bool(checked))
        self.cfg.save()
        self._post("/mic/enable", {"on": bool(checked)})

    def _toggle_desktop(self, checked: bool) -> None:
        self.cfg.set("panel_desktop", bool(checked))
        self.cfg.save()
        self._post("/desktop/enable", {"on": bool(checked)})

    def _save_int(self, key: str, value: int) -> None:
        self.cfg.set(key, int(value))
        self.cfg.save()

    def _voice_changed(self, _index: int) -> None:
        value = self.voice_combo.currentData()
        if value:
            self.cfg.set("voice_chime_voice", str(value))
            self.cfg.save()

    # ---------- 动作 ----------
    def _open_chat(self) -> None:
        if callable(self._on_open_chat):
            self._on_open_chat()

    def _restart(self) -> None:
        if callable(self._on_restart):
            self._on_restart()

    # ---------- 无边框拖动 ----------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None
        super().mouseReleaseEvent(event)
