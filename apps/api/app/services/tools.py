from __future__ import annotations

import asyncio
import base64
import html
import ipaddress
import re
import textwrap
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import IMAGE_DIR, SANDBOX_DIR, settings


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

IMAGE_SIZE_PATTERN = re.compile(r"^(\d{3,4})x(\d{3,4})$")


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


def get_image_runtime_source() -> str:
    return "remote" if settings.image_base_url and settings.image_api_key else "stub"


def _parse_image_size(size: str) -> tuple[int, int]:
    match = IMAGE_SIZE_PATTERN.match(size.strip().lower())
    if not match:
        return 1024, 1024
    return int(match.group(1)), int(match.group(2))


def _wrap_prompt_lines(prompt: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", prompt.strip()) or "未提供提示词"
    lines = textwrap.wrap(normalized, width=26)
    return lines[:8] if lines else [normalized]


def _build_local_image(prompt: str, style: str | None, size: str) -> dict:
    width, height = _parse_image_size(size)
    filename = f"image_{uuid4().hex}.svg"
    target = IMAGE_DIR / filename
    title = html.escape("Agent Core Image")
    style_text = html.escape(style or "default")
    prompt_lines = [html.escape(line) for line in _wrap_prompt_lines(prompt)]
    line_elements = []
    y = 246
    for line in prompt_lines:
        line_elements.append(f'<text x="72" y="{y}" class="prompt-line">{line}</text>')
        y += 38
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#121826"/>
      <stop offset="55%" stop-color="#20344f"/>
      <stop offset="100%" stop-color="#3a5a80"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#f9c74f"/>
      <stop offset="100%" stop-color="#f9844a"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="16" stdDeviation="18" flood-color="#000000" flood-opacity="0.32"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <circle cx="{int(width * 0.79)}" cy="{int(height * 0.22)}" r="{int(min(width, height) * 0.16)}" fill="#f9c74f" opacity="0.14"/>
  <circle cx="{int(width * 0.18)}" cy="{int(height * 0.78)}" r="{int(min(width, height) * 0.22)}" fill="#90be6d" opacity="0.10"/>
  <rect x="48" y="48" width="{width - 96}" height="{height - 96}" rx="34" fill="#0f1724" fill-opacity="0.72" stroke="rgba(255,255,255,0.14)" filter="url(#shadow)"/>
  <rect x="72" y="78" width="240" height="10" rx="5" fill="url(#accent)"/>
  <text x="72" y="148" class="title">{title}</text>
  <text x="72" y="188" class="meta">style: {style_text}</text>
  <text x="72" y="224" class="meta">prompt</text>
  {''.join(line_elements)}
  <text x="72" y="{height - 78}" class="footer">local fallback render · {width}x{height}</text>
  <style>
    .title {{ fill: #ffffff; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 34px; font-weight: 700; letter-spacing: 0.02em; }}
    .meta {{ fill: #d8e4f0; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 18px; opacity: 0.88; }}
    .prompt-line {{ fill: #f8fafc; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 26px; font-weight: 600; }}
    .footer {{ fill: #cbd5e1; font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 15px; opacity: 0.75; }}
  </style>
</svg>"""
    target.write_text(svg, encoding="utf-8")
    return {
        "status": "success",
        "prompt": prompt,
        "style": style or "default",
        "size": f"{width}x{height}",
        "source": "stub",
        "format": "svg",
        "image_url": f"/static/images/{filename}",
    }


async def _build_remote_image(prompt: str, style: str | None, size: str) -> dict:
    payload = {
        "model": settings.image_model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }
    if style:
        payload["style"] = style
    headers = {
        "Authorization": f"Bearer {settings.image_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=settings.image_timeout_seconds) as client:
        response = await client.post(
            f"{settings.image_base_url.rstrip('/')}/images/generations",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    image_data = (data.get("data") or [{}])[0]
    image_url = image_data.get("url")
    image_b64 = image_data.get("b64_json")

    if image_b64:
        filename = f"image_{uuid4().hex}.png"
        target = IMAGE_DIR / filename
        target.write_bytes(base64.b64decode(image_b64))
        return {
            "status": "success",
            "prompt": prompt,
            "style": style or "default",
            "size": size,
            "source": "remote",
            "format": "png",
            "image_url": f"/static/images/{filename}",
            "model": settings.image_model,
        }

    if image_url:
        parsed = urlparse(image_url)
        extension = Path(parsed.path).suffix or ".png"
        filename = f"image_{uuid4().hex}{extension}"
        target = IMAGE_DIR / filename
        try:
            async with httpx.AsyncClient(timeout=settings.image_timeout_seconds) as client:
                image_response = await client.get(image_url)
                image_response.raise_for_status()
            target.write_bytes(image_response.content)
            return {
                "status": "success",
                "prompt": prompt,
                "style": style or "default",
                "size": size,
                "source": "remote",
                "format": extension.lstrip(".") or "png",
                "image_url": f"/static/images/{filename}",
                "model": settings.image_model,
            }
        except Exception:
            return {
                "status": "success",
                "prompt": prompt,
                "style": style or "default",
                "size": size,
                "source": "remote",
                "format": "url",
                "image_url": image_url,
                "model": settings.image_model,
            }

    raise ValueError("Image generation response does not contain image data")


async def image_generation_tool(prompt: str, style: str | None = None, size: str = "1024x1024") -> dict:
    if settings.image_base_url and settings.image_api_key:
        try:
            return await _build_remote_image(prompt, style, size)
        except Exception:
            pass
    return _build_local_image(prompt, style, size)


async def generate_image(prompt: str, style: str | None = None, size: str = "1024x1024") -> dict:
    return await image_generation_tool(prompt=prompt, style=style, size=size)


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
