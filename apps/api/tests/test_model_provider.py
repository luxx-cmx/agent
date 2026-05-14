import json

import pytest

from app.services import model_provider


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


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
        return FakeResponse(
            {
                "choices": [{"message": {"content": "mimo-ok"}}],
                "usage": {"total_tokens": 12},
            }
        )


def test_normalize_mimo_model_name() -> None:
    assert model_provider.normalize_mimo_model_name("MiMo-V2.5-Pro") == "mimo-v2.5-pro"


def test_stub_provider_when_mimo_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_provider.settings, "mimo_base_url", None)
    monkeypatch.setattr(model_provider.settings, "mimo_api_key", None)

    result = asyncio_run(model_provider.provider.complete(model="MiMo-V2.5-Pro", messages=[{"role": "user", "content": "hi"}], tools_used=[]))

    assert result["source"] == "stub"


def test_provider_uses_normalized_model_for_mimo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model_provider.settings, "mimo_base_url", "https://example.com/v1")
    monkeypatch.setattr(model_provider.settings, "mimo_api_key", "test-key")
    monkeypatch.setattr(model_provider.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio_run(model_provider.provider.complete(model="MiMo-V2.5-Pro", messages=[{"role": "user", "content": "hi"}], tools_used=[]))

    assert result["source"] == "mimo"
    assert result["content"] == "mimo-ok"
    assert FakeAsyncClient.last_json is not None
    assert FakeAsyncClient.last_json["model"] == "mimo-v2.5-pro"


def asyncio_run(awaitable):
    import asyncio

    return asyncio.run(awaitable)