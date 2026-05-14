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