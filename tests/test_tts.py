from __future__ import annotations

import base64
import io
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.tts import SpeechRequest, SpeechService, SpeechServiceError, VoiceProfile
from src.tts.providers import (
    EdgeTtsProvider,
    ProviderAudio,
    ProviderError,
    _openai_speech_url,
)
from src.webui.config_update import prepare_config_update
from src.webui.services.speech import (
    SpeechDependencies,
    WebSpeechService,
    _is_public_game_text,
)


def _config(**changes):
    value = {
        "tts_provider": "openai-compatible",
        "tts_base_url": "http://127.0.0.1:8880/v1",
        "tts_api_key": "",
        "tts_model": "kokoro",
        "tts_audio_format": "mp3",
        "tts_default_voice": "alloy",
        "tts_timeout_seconds": 30,
        "tts_cache_mb": 16,
    }
    value.update(changes)
    return value


class _FakeProvider:
    def __init__(self):
        self.calls = 0
        self.voices = []

    async def synthesize(self, request, voice):
        self.calls += 1
        self.voices.append(voice)
        return ProviderAudio(body=f"audio:{request.text}".encode(), content_type="audio/mpeg")


def _wav_payload(seconds: float = 1.0) -> str:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * int(16000 * seconds))
    return base64.b64encode(output.getvalue()).decode("ascii")


@pytest.mark.asyncio
async def test_speech_service_caches_identical_requests(tmp_path, monkeypatch):
    service = SpeechService(_config(), tmp_path / "cache")
    provider = _FakeProvider()
    monkeypatch.setattr(service, "_provider", lambda: provider)
    request = SpeechRequest(text="篝火亮了", voice="alloy", language="zh-CN", speed=1.0)

    first = await service.synthesize(request)
    second = await service.synthesize(request)

    assert first.body == "audio:篝火亮了".encode()
    assert first.cached is False
    assert second.cached is True
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_gpt_sovits_requires_personal_voice_or_optional_preset(tmp_path):
    service = SpeechService(
        _config(tts_provider="gpt-sovits", tts_base_url="http://127.0.0.1:9880"),
        tmp_path / "cache",
    )

    with pytest.raises(SpeechServiceError, match="个人音色或已安装的音色预设"):
        await service.synthesize(SpeechRequest(text="测试", voice="missing"), [])


@pytest.mark.asyncio
async def test_personal_gpt_sovits_reference_works_without_plugin_pack(tmp_path, monkeypatch):
    service = SpeechService(
        _config(tts_provider="gpt-sovits", tts_base_url="http://127.0.0.1:9880"),
        tmp_path / "cache",
    )
    saved = service.save_voice_profile(
        "",
        {
            "name": "个人旁白",
            "engine": "gpt-sovits",
            "prompt_text": "篝火已经点亮。",
            "prompt_language": "zh-CN",
        },
        file_data=_wav_payload(),
        file_name="narrator.wav",
    )
    provider = _FakeProvider()
    monkeypatch.setattr(service, "_provider", lambda: provider)

    result = await service.synthesize(
        SpeechRequest(text="新的冒险开始了。", voice=saved["id"]),
        service.personal_voice_profiles(),
    )

    assert result.body.startswith(b"audio:")
    assert provider.voices[0].source == "personal"
    assert provider.voices[0].reference_audio.is_file()
    assert service.editable_voice_profiles()[0]["has_reference_audio"] is True
    assert "_reference_audio_path" not in service.editable_voice_profiles()[0]


def test_personal_openai_voice_id_and_server_reference_are_provider_native(tmp_path):
    service = SpeechService(_config(), tmp_path / "cache")
    openai_voice = service.save_voice_profile(
        "",
        {"name": "AllTalk Alice", "engine": "openai-compatible", "voice_id": "alice.wav"},
    )
    gpt_voice = service.save_voice_profile(
        "",
        {
            "name": "容器旁白",
            "engine": "gpt-sovits",
            "prompt_text": "测试文本",
            "server_reference_path": "/reference/narrator.wav",
        },
    )

    runtime = {profile["id"]: profile for profile in service.personal_voice_profiles()}
    assert runtime[openai_voice["id"]]["voice_id"] == "alice.wav"
    assert runtime[gpt_voice["id"]]["reference_audio_path"] == "/reference/narrator.wav"


def test_deleting_personal_voice_removes_unused_reference(tmp_path):
    service = SpeechService(_config(), tmp_path / "cache")
    saved = service.save_voice_profile(
        "",
        {
            "name": "临时音色",
            "engine": "gpt-sovits",
            "prompt_text": "测试文本",
        },
        file_data=_wav_payload(),
        file_name="voice.wav",
    )
    reference = Path(service.personal_voice_profiles()[0]["_reference_audio_path"])

    service.delete_voice_profile(saved["id"])

    assert service.editable_voice_profiles() == []
    assert not reference.exists()


@pytest.mark.asyncio
async def test_removed_plugin_voice_does_not_leak_runtime_id_upstream(tmp_path):
    service = SpeechService(_config(), tmp_path / "cache")

    with pytest.raises(SpeechServiceError, match="未安装或未启用"):
        await service.synthesize(
            SpeechRequest(text="测试", voice="plugin:gone:voice:narrator"),
            [],
        )


def test_browser_provider_needs_no_server_url(tmp_path):
    service = SpeechService(_config(tts_provider="browser", tts_base_url=""), tmp_path / "cache")

    assert service.backend_enabled is False
    assert service.public_config()["provider"] == "browser"


def test_local_tts_endpoint_bypasses_global_proxy(tmp_path):
    service = SpeechService(
        _config(tts_base_url="http://192.168.1.12:8880/v1"),
        tmp_path / "cache",
        proxy_url="http://proxy.example:8080",
    )

    assert service.proxy_url == ""


def test_game_speech_accepts_rendered_public_chunks_only():
    instance = SimpleNamespace(log=[{
        "gm_response": "**火焰**升起。\n---\nSTATE:heat:+1",
        "actions": [{"user_id": "p1", "text": "我检查门锁 [d20=12]"}],
    }])

    assert _is_public_game_text(instance, "火焰升起") is True
    assert _is_public_game_text(instance, "我检查门锁") is True
    assert _is_public_game_text(instance, "请替我朗读任意付费文本") is False


def test_openai_speech_url_accepts_root_v1_and_full_endpoint():
    assert _openai_speech_url("https://example.test") == "https://example.test/v1/audio/speech"
    assert _openai_speech_url("https://example.test/v1") == "https://example.test/v1/audio/speech"
    assert _openai_speech_url("https://example.test/v1/audio/speech") == "https://example.test/v1/audio/speech"


def _edge_provider() -> EdgeTtsProvider:
    return EdgeTtsProvider(
        base_url="", api_key="", model="", audio_format="mp3", timeout_seconds=30,
    )


class _RecordingCommunicate:
    def __init__(self, text: str, voice: str, *, rate: str, proxy: str | None, **_: Any) -> None:
        self.kwargs = {"text": text, "voice": voice, "rate": rate, "proxy": proxy}

    async def stream(self):
        yield {"type": "WordBoundary", "text": "测"}
        yield {"type": "audio", "data": b"mp3-a"}
        yield {"type": "audio", "data": b"mp3-b"}


@pytest.mark.asyncio
async def test_edge_tts_provider_maps_request_to_communicate(monkeypatch):
    import edge_tts

    instances: list[_RecordingCommunicate] = []

    def factory(*args, **kwargs):
        instance = _RecordingCommunicate(*args, **kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(edge_tts, "Communicate", factory)
    provider = _edge_provider()

    audio = await provider.synthesize(SpeechRequest(text="你好", voice="", speed=1.5), None)

    assert audio.body == b"mp3-amp3-b"
    assert audio.content_type == "audio/mpeg"
    assert instances[0].kwargs == {
        "text": "你好",
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "+50%",
        "proxy": None,
    }


@pytest.mark.asyncio
async def test_edge_tts_provider_prefers_profile_voice_id(monkeypatch):
    import edge_tts

    instances: list[_RecordingCommunicate] = []

    def factory(*args, **kwargs):
        instance = _RecordingCommunicate(*args, **kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(edge_tts, "Communicate", factory)
    profile = VoiceProfile(id="personal:edge", name="七海", engine="edge-tts", voice_id="ja-JP-NanamiNeural")

    await _edge_provider().synthesize(SpeechRequest(text="テスト", voice="zh-CN-YunxiNeural"), profile)

    assert instances[0].kwargs["voice"] == "ja-JP-NanamiNeural"


@pytest.mark.asyncio
async def test_edge_tts_provider_rejects_non_neural_voice():
    with pytest.raises(ProviderError, match="Neural"):
        await _edge_provider().synthesize(SpeechRequest(text="测试", voice="alloy"), None)


@pytest.mark.asyncio
async def test_edge_tts_provider_rejects_empty_audio(monkeypatch):
    import edge_tts

    class _SilentCommunicate:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def stream(self):
            yield {"type": "WordBoundary", "text": "静"}

    monkeypatch.setattr(edge_tts, "Communicate", _SilentCommunicate)

    with pytest.raises(ProviderError, match="空音频"):
        await _edge_provider().synthesize(SpeechRequest(text="测试"), None)


@pytest.mark.asyncio
async def test_edge_tts_provider_wraps_upstream_errors(monkeypatch):
    from edge_tts.exceptions import EdgeTTSException

    class _BrokenCommunicate:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def stream(self):
            raise EdgeTTSException("websocket closed")
            yield {"type": "audio", "data": b""}  # pragma: no cover

    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", _BrokenCommunicate)

    with pytest.raises(ProviderError, match="Edge TTS 合成失败"):
        await _edge_provider().synthesize(SpeechRequest(text="测试"), None)


def test_edge_tts_needs_no_base_url_or_api_key(tmp_path):
    service = SpeechService(
        _config(tts_provider="edge-tts", tts_base_url="", tts_api_key=""),
        tmp_path / "cache",
    )

    assert service.backend_enabled is True
    assert isinstance(service._provider(), EdgeTtsProvider)


def test_edge_tts_provider_passes_runtime_config_update():
    result = prepare_config_update({"tts_provider": "browser"}, {"tts_provider": "edge-tts"})

    assert result.error == ""
    assert result.state["tts_provider"] == "edge-tts"


def test_edge_tts_builtin_voice_catalog(tmp_path):
    service = SpeechService(_config(tts_provider="edge-tts", tts_base_url=""), tmp_path / "cache")
    web_speech = WebSpeechService(SpeechDependencies(
        backend=service,
        plugin_host=None,
        get_instance=lambda _key: None,
        parse_game_key=lambda raw: (raw,),
    ))

    catalog = web_speech.list_voices()
    voices = {voice["id"]: voice for voice in catalog["voices"]}

    assert catalog["provider"] == "edge-tts"
    assert voices["zh-CN-XiaoxiaoNeural"]["engine"] == "edge-tts"
    assert voices["zh-CN-XiaoxiaoNeural"]["name"].startswith("晓晓")
    assert voices["zh-CN-XiaoxiaoNeural"]["language"] == "zh-CN"
    assert voices["ja-JP-NanamiNeural"]["language"] == "ja-JP"


@pytest.mark.asyncio
async def test_edge_tts_personal_voice_alias_synthesizes(tmp_path, monkeypatch):
    service = SpeechService(_config(tts_provider="edge-tts", tts_base_url=""), tmp_path / "cache")
    saved = service.save_voice_profile(
        "",
        {"name": "韩语女声", "engine": "edge-tts", "voice_id": "ko-KR-SunHiNeural"},
    )
    provider = _FakeProvider()
    monkeypatch.setattr(service, "_provider", lambda: provider)

    result = await service.synthesize(
        SpeechRequest(text="测试", voice=saved["id"]),
        service.personal_voice_profiles(),
    )

    assert result.body.startswith(b"audio:")
    assert provider.voices[0].voice_id == "ko-KR-SunHiNeural"
    assert provider.voices[0].source == "personal"


def test_edge_tts_personal_voice_requires_voice_id(tmp_path):
    service = SpeechService(_config(tts_provider="edge-tts", tts_base_url=""), tmp_path / "cache")

    with pytest.raises(ValueError, match="voice ID"):
        service.save_voice_profile("", {"name": "缺 ID", "engine": "edge-tts"})
