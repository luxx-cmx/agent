import asyncio

import pytest

from app.core.config import settings
from app.services import tools
from app.services.tools import database_query_tool, image_generation_tool


pytestmark = pytest.mark.skipif(not settings.database_url, reason="DATABASE_URL 未配置")


def test_database_query_tool_executes_real_select() -> None:
    result = asyncio.run(database_query_tool("select current_database() as database_name"))

    assert result["status"] == "success"
    assert result["row_count"] == 1
    assert result["rows"][0]["database_name"] == "agent"


def test_database_query_tool_rejects_write_sql() -> None:
    result = asyncio.run(database_query_tool("update conversations set title = 'x'"))

    assert result["status"] == "failed"
    assert "只允许" in result["error"] or "拒绝执行" in result["error"]


def test_image_generation_tool_builds_local_svg(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(tools.settings, "image_base_url", None)
    monkeypatch.setattr(tools.settings, "image_api_key", None)
    monkeypatch.setattr(tools, "IMAGE_DIR", tmp_path)

    result = asyncio.run(image_generation_tool("生成一张赛博城市夜景海报", style="霓虹", size="1024x1024"))

    assert result["status"] == "success"
    assert result["source"] == "stub"
    assert result["format"] == "svg"
    assert result["image_url"].endswith(".svg")
    assert (tmp_path / result["image_url"].split("/")[-1]).exists()