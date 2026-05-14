import base64

import pytest

from app.core.schemas import TTSRequest
from app.services import tts_service


class FakeTTSResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "audio": {
                            "data": base64.b64encode(b"RIFFdemo-wave").decode("ascii"),
                        }
                    }
                }
            ]
        }


class FakeAsyncClient:
    last_json: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, headers: dict, json: dict):
        FakeAsyncClient.last_json = json
        return FakeTTSResponse()


def test_tts_uses_mimo_chat_completions(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(tts_service.settings, "mimo_base_url", "https://example.com/v1")
    monkeypatch.setattr(tts_service.settings, "mimo_api_key", "test-key")
    monkeypatch.setattr(tts_service, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(tts_service.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio_run(tts_service.synthesize_tts(TTSRequest(model="MiMo-V2.5-TTS", input="hello world")))

    assert result.source == "mimo"
    assert result.audio_url.endswith(".wav")
    assert FakeAsyncClient.last_json is not None
    assert FakeAsyncClient.last_json["model"] == "mimo-v2.5-tts"
    assert FakeAsyncClient.last_json["messages"][0]["role"] == "assistant"


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)