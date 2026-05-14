from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings


def normalize_mimo_model_name(model: str) -> str:
    return model.strip().lower()


def get_llm_runtime_source() -> str:
    return "mimo" if settings.mimo_base_url and settings.mimo_api_key else "stub"


class StubProvider:
    async def complete(self, model: str, messages: list[dict[str, Any]], tools_used: list[dict[str, Any]]) -> dict[str, Any]:
        user_input = str(messages[-1]["content"]) if messages else ""
        tool_text = ""
        if tools_used:
            fragments = [f"{tool['tool_id']} => {tool['result']}" for tool in tools_used]
            tool_text = "\n\n工具观察：" + "\n".join(fragments)
        content = (
            f"已使用模型 {model} 处理请求。"
            f"\n\n用户问题：{user_input[:500]}"
            f"\n\n结论：这是一个基于 ReAct 的演示响应，可替换为真实 MiMo 调用。"
            f"{tool_text}"
        )
        thought = "先根据问题识别所需工具，再汇总 Observation 输出结构化结果。"
        return {
            "content": content,
            "thought": thought,
            "tokens_used": max(80, len(content) // 2),
            "source": "stub",
            "resolved_model": model,
        }


class MimoOpenAICompatibleProvider:
    async def complete(self, model: str, messages: list[dict[str, Any]], tools_used: list[dict[str, Any]]) -> dict[str, Any]:
        if not settings.mimo_base_url or not settings.mimo_api_key:
            return await StubProvider().complete(model, messages, tools_used)

        normalized_model = normalize_mimo_model_name(model)
        payload = {
            "model": normalized_model,
            "messages": messages,
            "temperature": 0.3,
            "stream": False,
            "tools_context": tools_used,
        }
        headers = {
            "Authorization": f"Bearer {settings.mimo_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=settings.mimo_timeout_seconds) as client:
            response = await client.post(f"{settings.mimo_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})
        return {
            "content": message.get("content", json.dumps(message, ensure_ascii=False)),
            "thought": "通过 MiMo OpenAI 兼容接口生成。",
            "tokens_used": usage.get("total_tokens", 0),
            "source": "mimo",
            "resolved_model": normalized_model,
        }


provider = MimoOpenAICompatibleProvider()