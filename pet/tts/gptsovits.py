# -*- coding: utf-8 -*-
"""GPT-SoVITS 语音后端：本地服务（api_v2.py）或任意兼容 HTTP 接口。

接入方式（与 ``pet/tts/base.py`` 的约定一致）：
- ``url``：GPT-SoVITS 的 API 根地址，默认本机 9880；
- ``install_dir``：本地 GPT-SoVITS 目录（含 ``api_v2.py`` 与 ``env\\python.exe``）。
  只用于面板上的「一键启动」和路径检测，合成本身只认 url；
- ``ref_audio`` / ``prompt_text`` / ``prompt_lang`` / ``text_lang``：api_v2 的
  参考音频与语言参数，和直播那套用的是同一组字段。

离线可单测的部分（``plan`` / ``flavor`` / ``availability``）不联网；``synth`` 才发请求，
失败抛 ``TtsUnavailable``，由服务层回退到下一个后端。
"""

from __future__ import annotations

import json
import urllib.request

from .base import TtsField, TtsProvider, TtsUnavailable, register

PROVIDER_ID = "gptsovits"
LABEL = "GPT-SoVITS（本地 / API）"
DEFAULT_URL = "http://127.0.0.1:9880"
DEFAULT_DIR = r"C:\GPT-SoVITS"
AVAILABILITY_CODE = "gptsovits_missing"
MISSING_MESSAGE = (
    "GPT-SoVITS 服务连不上。确认 api_v2.py 已启动（默认 9880），"
    "或在面板里填好服务地址和参考音频。"
)

LANG_CHOICES = (("zh", "中文"), ("en", "英文"), ("ja", "日文"), ("ko", "韩文"), ("yue", "粤语"))


def _select(name: str, key: str, label: str, default: str, hint: str = "") -> TtsField:
    return TtsField(name=name, key=key, label=label, hint=hint, kind="select",
                    default=default, options=LANG_CHOICES)


class GptSoVitsProvider(TtsProvider):
    id = PROVIDER_ID
    label = LABEL
    unavailable_message = MISSING_MESSAGE
    availability_code = AVAILABILITY_CODE
    fields = (
        TtsField(name="url", key="voice_chime_gptsovits_url", label="服务地址",
                 hint="默认 http://127.0.0.1:9880；远程 API 填对方地址",
                 default=DEFAULT_URL, placeholder="http://127.0.0.1:9880"),
        TtsField(name="install_dir", key="voice_chime_gptsovits_dir", label="本地目录",
                 hint="含 api_v2.py 的 GPT-SoVITS 目录，用于一键启动；可以留空",
                 default=DEFAULT_DIR),
        TtsField(name="ref_audio", key="voice_chime_gptsovits_ref_audio", label="参考音频",
                 hint="api_v2 的 ref_audio_path，例如 C:\\GPT-SoVITS\\参考\\主唱.wav",
                 default=""),
        TtsField(name="prompt_text", key="voice_chime_gptsovits_prompt_text", label="参考文本",
                 hint="参考音频对应的一句话，留空时用 api_v2 的默认逻辑",
                 default=""),
        _select("prompt_lang", "voice_chime_gptsovits_prompt_lang", "参考语言", "zh"),
        _select("text_lang", "voice_chime_gptsovits_text_lang", "合成语言", "zh"),
    )

    def plan(self, values: dict) -> dict:
        return {
            "url": str(values.get("url") or DEFAULT_URL).rstrip("/"),
            "ref_audio": str(values.get("ref_audio") or ""),
            "prompt_text": str(values.get("prompt_text") or ""),
            "prompt_lang": str(values.get("prompt_lang") or "zh"),
            "text_lang": str(values.get("text_lang") or "zh"),
            "ext": "wav",
        }

    def flavor(self, values: dict) -> str:
        return "|".join((
            str(values.get("url") or DEFAULT_URL),
            str(values.get("ref_audio") or ""),
            str(values.get("prompt_text") or ""),
            str(values.get("prompt_lang") or "zh"),
            str(values.get("text_lang") or "zh"),
        ))

    def availability(self, values: dict) -> str:
        return "" if str(values.get("url") or "").strip() else AVAILABILITY_CODE

    def synth(self, text: str, plan: dict, out_path) -> None:
        payload = {
            "text": text,
            "text_lang": plan.get("text_lang") or "zh",
            "prompt_lang": plan.get("prompt_lang") or "zh",
            "streaming_mode": False,
        }
        if plan.get("ref_audio"):
            payload["ref_audio_path"] = plan["ref_audio"]
        if plan.get("prompt_text"):
            payload["prompt_text"] = plan["prompt_text"]
        request = urllib.request.Request(
            plan.get("url", DEFAULT_URL) + "/tts",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                audio = response.read()
        except Exception as error:  # 网络/服务端错误统一交给服务层回退
            raise TtsUnavailable(AVAILABILITY_CODE) from error
        if not audio:
            raise TtsUnavailable(AVAILABILITY_CODE)
        out_path = str(out_path)
        with open(out_path, "wb") as handle:
            handle.write(audio)


register(GptSoVitsProvider())
