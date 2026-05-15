from app.services.tools import build_database_sql_from_prompt
from app.services.agent_engine import agent_engine


def test_build_database_sql_from_prompt_for_messages() -> None:
    result = build_database_sql_from_prompt("查询最近的会话消息")

    assert result["status"] == "success"
    assert "messages" in result["matched_tables"]
    assert "conversations" in result["matched_tables"]
    assert "JOIN conversations" in result["sql"]


def test_resolve_generation_target_prefers_image_generation() -> None:
    assert agent_engine.resolve_generation_target("帮我生成一张赛博城市海报", None) == "image"