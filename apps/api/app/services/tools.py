from __future__ import annotations

import asyncio
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import SANDBOX_DIR, settings


QUERY_ROW_LIMIT = 50
PROMPT_ROW_LIMIT = 20
FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|comment|copy|call|execute|merge|vacuum|analyze|refresh)\b",
    re.IGNORECASE,
)
TABLE_KEYWORD_MAP = {
    "conversations": ["会话", "conversation", "chat", "标题", "system prompt"],
    "messages": ["消息", "message", "对话", "assistant", "user", "role", "内容"],
    "agent_configs": ["配置", "config", "模型", "temperature", "memory", "迭代"],
}


def _normalize_database_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


DATABASE_ENGINE = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True) if settings.database_url else None


def _validate_readonly_sql(sql: str) -> tuple[bool, str]:
    normalized = sql.strip().rstrip(";").strip()
    lowered = normalized.lower()
    if not normalized:
        return False, "SQL 不能为空"
    if not (lowered.startswith("select") or lowered.startswith("with")):
        return False, "只允许执行 SELECT 或 WITH 查询"
    if FORBIDDEN_SQL_PATTERN.search(normalized):
        return False, "检测到潜在写操作关键词，已拒绝执行"
    return True, normalized


def get_database_schema_summary() -> dict:
    if DATABASE_ENGINE is None:
        return {"status": "failed", "error": "DATABASE_URL 未配置，数据库工具不可用"}

    try:
        inspector = inspect(DATABASE_ENGINE)
        tables = []
        for table_name in sorted(inspector.get_table_names(schema="public")):
            columns = [
                {"name": column["name"], "data_type": str(column["type"])}
                for column in inspector.get_columns(table_name, schema="public")
            ]
            tables.append({"name": table_name, "columns": columns})
        return {"status": "success", "dialect": DATABASE_ENGINE.dialect.name, "tables": tables}
    except SQLAlchemyError as exc:
        return {"status": "failed", "error": str(exc)}


def build_database_sql_from_prompt(prompt: str) -> dict:
    schema = get_database_schema_summary()
    if schema["status"] != "success":
        return {"status": "failed", "error": schema.get("error", "无法读取数据库 schema")}

    lowered_prompt = prompt.lower()
    tables: list[dict] = schema["tables"]
    table_names = {table["name"] for table in tables}

    matched_tables = []
    for table in tables:
        table_name = table["name"]
        column_names = [column["name"].lower() for column in table["columns"]]
        table_keywords = TABLE_KEYWORD_MAP.get(table_name, [])
        if table_name.lower() in lowered_prompt:
            matched_tables.append(table)
            continue
        if any(keyword in lowered_prompt for keyword in table_keywords):
            matched_tables.append(table)
            continue
        if any(column_name in lowered_prompt for column_name in column_names):
            matched_tables.append(table)

    deduped_tables = []
    seen_names = set()
    for table in matched_tables:
        if table["name"] not in seen_names:
            deduped_tables.append(table)
            seen_names.add(table["name"])
    matched_tables = deduped_tables

    if not matched_tables:
        preferred_order = [name for name in ["messages", "conversations", "agent_configs"] if name in table_names]
        matched_tables = [next(table for table in tables if table["name"] == name) for name in preferred_order[:1]] or tables[:1]

    matched_names = [table["name"] for table in matched_tables]

    if {"messages", "conversations"}.issubset(set(matched_names)):
        filters = []
        if "assistant" in lowered_prompt:
            filters.append("m.role = 'assistant'")
        if "user" in lowered_prompt or "用户" in prompt:
            filters.append("m.role = 'user'")
        if any(keyword in prompt for keyword in ["今天", "近一天", "24小时"]):
            filters.append("m.created_at >= now() - interval '1 day'")
        if any(keyword in prompt for keyword in ["最近", "最新"]):
            order_by = "m.created_at DESC"
        else:
            order_by = "c.updated_at DESC"
        if any(keyword in prompt for keyword in ["数量", "多少", "统计", "count"]):
            sql = (
                "SELECT c.id AS conversation_id, c.title, COUNT(m.id) AS message_count "
                "FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id "
                f"{'WHERE ' + ' AND '.join(filters) if filters else ''} "
                "GROUP BY c.id, c.title ORDER BY message_count DESC LIMIT 20"
            )
        else:
            sql = (
                "SELECT c.id AS conversation_id, c.title, m.role, m.model, m.created_at, m.content_json "
                "FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                f"{'WHERE ' + ' AND '.join(filters) if filters else ''} "
                f"ORDER BY {order_by} LIMIT {PROMPT_ROW_LIMIT}"
            )
        return {
            "status": "success",
            "sql": sql,
            "matched_tables": matched_names,
            "schema_excerpt": matched_tables,
        }

    table = matched_tables[0]
    table_name = table["name"]
    column_names = [column["name"] for column in table["columns"]]
    selected_columns = ", ".join(column_names[: min(6, len(column_names))]) or "*"
    order_by = ""
    if "created_at" in column_names:
        order_by = " ORDER BY created_at DESC"
    elif "updated_at" in column_names:
        order_by = " ORDER BY updated_at DESC"

    if any(keyword in prompt for keyword in ["数量", "多少", "统计", "count"]):
        sql = f"SELECT COUNT(*) AS total FROM {table_name}"
    else:
        sql = f"SELECT {selected_columns} FROM {table_name}{order_by} LIMIT {PROMPT_ROW_LIMIT}"

    return {
        "status": "success",
        "sql": sql,
        "matched_tables": [table_name],
        "schema_excerpt": matched_tables,
    }


async def web_search_tool(query: str) -> dict:
    return {
        "query": query,
        "results": [
            {
                "title": f"{query} - 市场观察",
                "snippet": "本地演示模式下返回模拟摘要，实际部署时可替换为真实搜索引擎适配器。",
                "url": "https://example.com/report",
            }
        ],
    }


async def code_interpreter_tool(task: str) -> dict:
    if "fastapi" in task.lower():
        summary = "建议生成 POST 上传接口、文件大小校验和返回 URL。"
    else:
        summary = f"已分析任务：{task[:120]}"
    return {"task": task, "summary": summary, "status": "completed"}


async def database_query_tool(sql: str) -> dict:
    is_valid, normalized_or_error = _validate_readonly_sql(sql)
    if not is_valid:
        return {"status": "failed", "error": normalized_or_error}
    if DATABASE_ENGINE is None:
        return {"status": "failed", "error": "DATABASE_URL 未配置，数据库工具不可用"}

    readonly_query = normalized_or_error
    wrapped_query = f"SELECT * FROM ({readonly_query}) AS agent_core_query LIMIT {QUERY_ROW_LIMIT}"

    try:
        with DATABASE_ENGINE.connect() as connection:
            transaction = connection.begin()
            try:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                result = connection.execute(text(wrapped_query))
                rows = [dict(row._mapping) for row in result]
            finally:
                transaction.rollback()
    except SQLAlchemyError as exc:
        return {
            "status": "failed",
            "error": "数据库查询执行失败",
            "detail": str(exc),
        }

    return {
        "status": "success",
        "sql": readonly_query,
        "row_count": len(rows),
        "truncated": len(rows) == QUERY_ROW_LIMIT,
        "rows": rows,
    }


def _is_private_host(hostname: str | None) -> bool:
    if not hostname:
        return True
    if hostname in {"localhost", "127.0.0.1"}:
        return True
    try:
        address = ipaddress.ip_address(hostname)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        return hostname.endswith(".local")


async def api_caller_tool(url: str, method: str = "GET") -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or _is_private_host(parsed.hostname):
        return {"status": "failed", "error": "目标地址不在允许范围内"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method.upper(), url)
    return {
        "status": "success",
        "status_code": response.status_code,
        "body_preview": response.text[:400],
    }


def _safe_path(path: str) -> Path:
    resolved = (SANDBOX_DIR / path).resolve()
    if SANDBOX_DIR not in resolved.parents and resolved != SANDBOX_DIR:
        raise ValueError("非法路径")
    return resolved


async def file_manager_tool(action: str, path: str, content: str | None = None) -> dict:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if action == "read":
        return {"status": "success", "content": target.read_text(encoding="utf-8") if target.exists() else ""}
    if action == "write":
        target.write_text(content or "", encoding="utf-8")
        return {"status": "success", "path": str(target.relative_to(SANDBOX_DIR))}
    if action == "list":
        directory = target if target.is_dir() else target.parent
        return {"status": "success", "items": sorted(item.name for item in directory.iterdir()) if directory.exists() else []}
    return {"status": "failed", "error": "不支持的文件操作"}


async def run_tools_in_parallel(tasks: list[tuple[str, dict, callable]]) -> list[dict]:
    async def _run(tool_id: str, arguments: dict, handler: callable) -> dict:
        result = await handler(**arguments)
        return {"tool_id": tool_id, "arguments": arguments, "result": result}

    coroutines = [_run(tool_id, arguments, handler) for tool_id, arguments, handler in tasks]
    return await asyncio.gather(*coroutines)
