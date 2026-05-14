from app.services.tools import build_database_sql_from_prompt


def test_build_database_sql_from_prompt_for_messages() -> None:
    result = build_database_sql_from_prompt("查询最近的会话消息")

    assert result["status"] == "success"
    assert "messages" in result["matched_tables"]
    assert "conversations" in result["matched_tables"]
    assert "JOIN conversations" in result["sql"]