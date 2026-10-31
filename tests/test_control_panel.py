"""精简控制面板的烟雾测试：行数、开关落配置、语音合成滑块落配置。"""

from __future__ import annotations

import pytest

from pet.control_panel import PetControlPanel


class _Cfg:
    def __init__(self):
        self.data = {
            "chat_reply_voice_enabled": True,
            "voice_chime_voice": "zh-CN-XiaoxiaoNeural",
            "voice_chime_rate": 5,
            "voice_chime_volume": 70,
        }
        self.saved = 0

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        self.saved += 1
        return True


@pytest.fixture()
def panel():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    cfg = _Cfg()
    widget = PetControlPanel(cfg, on_open_chat=lambda: None, on_restart=lambda: None)
    widget._post = lambda path, payload: None  # 不真的打 HTTP
    yield widget, cfg
    widget.close()


def test_panel_has_only_pet_rows(panel):
    widget, _cfg = panel
    keys = set(widget._rows)
    assert keys == {"voice_reply", "mic", "desktop"}
    assert widget._rows["voice_reply"].isChecked() is True
    assert widget._rows["mic"].isChecked() is False


def test_toggles_persist(panel):
    widget, cfg = panel
    widget._rows["mic"].setChecked(True)
    widget._rows["desktop"].setChecked(True)
    assert cfg.data["panel_mic"] is True
    assert cfg.data["panel_desktop"] is True
    assert cfg.saved >= 2


def test_voice_settings_persist(panel):
    widget, cfg = panel
    widget.rate_slider.setValue(12)
    widget._save_int("voice_chime_rate", 12)
    widget.volume_slider.setValue(55)
    widget._save_int("voice_chime_volume", 55)
    assert cfg.data["voice_chime_rate"] == 12
    assert cfg.data["voice_chime_volume"] == 55
