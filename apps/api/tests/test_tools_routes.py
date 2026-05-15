import pytest

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


client = TestClient(app)
headers = {"Authorization": "Bearer agent-core-dev-token"}


def test_database_schema_route() -> None:
    response = client.get("/api/v1/tools/database/schema", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    if settings.database_url:
        assert payload["status"] == "success"
        assert any(table["name"] == "conversations" for table in payload["tables"])
    else:
        assert payload["status"] == "failed"


def test_database_query_route_rejects_write_sql() -> None:
    response = client.post(
        "/api/v1/tools/database/query",
        headers=headers,
        json={"sql": "delete from messages"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_image_generation_route_returns_local_svg(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app.services import tools as tools_module

    monkeypatch.setattr(tools_module.settings, "image_base_url", None)
    monkeypatch.setattr(tools_module.settings, "image_api_key", None)
    monkeypatch.setattr(tools_module, "IMAGE_DIR", tmp_path)

    response = client.post(
        "/api/v1/tools/image/generate",
        headers=headers,
        json={"prompt": "生成一张蓝色科技感海报", "style": "科技风", "size": "1024x1024"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["source"] == "stub"
    assert payload["image_url"].endswith(".svg")