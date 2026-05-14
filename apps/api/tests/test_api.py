from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
headers = {"Authorization": "Bearer agent-core-dev-token"}


def test_health_includes_runtime_providers() -> None:
    health = client.get("/health")

    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["store"] in {"memory", "postgresql"}
    assert payload["llm_provider"] in {"stub", "mimo"}
    assert payload["tts_provider"] in {"stub", "mimo"}


def test_conversation_lifecycle_and_message_flow() -> None:
    created = client.post(
        "/api/v1/conversations",
        headers=headers,
        json={"title": "测试会话", "system_prompt": "你是测试助手", "default_model": "MiMo-V2.5-Pro"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]

    listed = client.get("/api/v1/conversations", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    replied = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "查询最近一周销售数据并生成语音播报", "stream": False},
    )
    assert replied.status_code == 200
    payload = replied.json()
    assert payload["message"]["tool_calls"]
    assert payload["message"]["tts_audio_url"]

    detail = client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2


def test_tool_registry_and_agent_config() -> None:
    tools = client.get("/api/v1/tools", headers=headers)
    assert tools.status_code == 200
    assert tools.json()["count"] >= 6

    updated = client.put(
        "/api/v1/agent/config",
        headers=headers,
        json={"model": "MiMo-V2.5", "memory_window": 10},
    )
    assert updated.status_code == 200
    assert updated.json()["model"] == "MiMo-V2.5"