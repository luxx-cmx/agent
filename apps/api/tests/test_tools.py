import asyncio

import pytest

from app.core.config import settings
from app.services.tools import database_query_tool


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