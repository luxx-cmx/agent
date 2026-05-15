from __future__ import annotations

import json
import re
import time
from typing import Any

from app.core.schemas import Message, ToolCall
from app.services.model_provider import provider
from app.services.store import store
from app.services.tools import (
    api_caller_tool,
    build_database_sql_from_prompt,
    code_interpreter_tool,
    database_query_tool,
    file_manager_tool,
    image_generation_tool,
    run_tools_in_parallel,
    web_search_tool,
)
from app.services.tts_service import synthesize_tts
from app.core.schemas import TTSRequest


class AgentEngine:
    TARGET_MODEL_MAP: dict[str, str] = {
        "auto": "MiMo-V2.5-Pro",
        "dialogue": "MiMo-V2.5-Pro",
        "analysis": "MiMo-V2.5-Pro",
        "search": "MiMo-V2-Omni",
        "code": "MiMo-V2.5-Pro",
        "multimodal": "MiMo-V2-Omni",
        "image": "MiMo-V2.5-Pro",
        "tts": "MiMo-V2.5-TTS",
        "voice_clone": "MiMo-V2.5-TTS-VoiceClone",
        "voice_design": "MiMo-V2.5-TTS-VoiceDesign",
    }

    IMAGE_TARGETS = {"image"}
    TTS_TARGETS = {"tts", "voice_clone", "voice_design"}

    TARGET_TITLES: dict[str, str] = {
        "auto": "自动路由",
        "dialogue": "单纯对话",
        "analysis": "数据报告",
        "search": "联网搜索",
        "code": "接口 / 代码",
        "multimodal": "图文解析",
        "image": "图片生成",
        "tts": "语音播报",
        "voice_clone": "声音克隆",
        "voice_design": "音色设计",
    }

    TARGET_TOOL_IDS: dict[str, list[str]] = {
        "auto": ["web_search", "database_query", "code_interpreter", "api_caller", "file_manager", "mimo_tts"],
        "dialogue": [],
        "analysis": ["database_query", "code_interpreter", "file_manager"],
        "search": ["web_search", "api_caller"],
        "code": ["code_interpreter", "api_caller", "file_manager"],
        "multimodal": ["web_search", "api_caller"],
        "image": ["image_generation"],
        "tts": ["mimo_tts"],
        "voice_clone": ["mimo_tts"],
        "voice_design": ["mimo_tts"],
    }

    def resolve_generation_target(self, prompt: str, generation_target: str | None) -> str:
        if generation_target and generation_target != "auto":
            return generation_target
        lowered = prompt.lower()
        if any(keyword in lowered for keyword in ["克隆", "复刻", "voice clone", "分身"]):
            return "voice_clone"
        if any(keyword in lowered for keyword in ["音色设计", "角色音", "风格音", "voice design"]):
            return "voice_design"
        if any(keyword in lowered for keyword in ["语音", "播报", "tts", "朗读", "配音"]):
            return "tts"
        if any(keyword in lowered for keyword in ["生图", "生成图片", "图片生成", "画一张", "绘图", "插画", "海报", "生成一张"]):
            return "image"
        if any(keyword in lowered for keyword in ["截图", "看图", "图像理解", "视觉", "多模态", "图片解析"]):
            return "multimodal"
        if any(keyword in lowered for keyword in ["代码", "接口", "api", "python", "脚本"]):
            return "code"
        if any(keyword in lowered for keyword in ["搜索", "联网", "网页", "资料", "检索"]):
            return "search"
        if any(keyword in lowered for keyword in ["报告", "总结", "分析", "数据", "环比", "销量", "报表"]):
            return "analysis"
        return "dialogue"

    def resolve_model_for_target(self, generation_target: str) -> str:
        return self.TARGET_MODEL_MAP.get(generation_target, "MiMo-V2.5-Pro")

    def describe_target(self, generation_target: str) -> str:
        return self.TARGET_TITLES.get(generation_target, generation_target)

    def _is_tts_target(self, generation_target: str) -> bool:
        return generation_target in self.TTS_TARGETS

    def _is_image_target(self, generation_target: str) -> bool:
        return generation_target in self.IMAGE_TARGETS

    def _extract_tts_text(self, prompt: str) -> str:
        patterns = [r"说的是[:：]?\s*(.+)$", r"内容[:：]?\s*(.+)$", r"播报[:：]?\s*(.+)$", r"读出[:：]?\s*(.+)$"]
        for pattern in patterns:
            match = re.search(pattern, prompt, flags=re.IGNORECASE | re.DOTALL)
            if match:
                candidate = match.group(1).strip(" \n\t'\"。！!？?")
                if candidate:
                    return candidate
        return prompt.strip()

    def _resolve_voice(self, prompt: str) -> tuple[str, str, float]:
        lowered = prompt.lower()
        if "娃娃音" in prompt or "child" in lowered:
            return ("child_female", "娃娃音", 1.1)
        if "男声" in prompt or "male" in lowered:
            return ("default-male", "男声", 1.0)
        return ("default-female", "女声", 1.0)

    def _render_tts_result(self, *, requested_model: str, tts_model: str, text: str, voice_label: str, speed: float, duration: float, source: str, audio_url: str) -> str:
        return (
            f"已使用模型 **{tts_model}** 处理请求。\n\n"
            "---\n\n"
            "## 语音合成请求\n\n"
            "### ReAct 执行流程\n\n"
            "| 步骤 | 动作 | 参数 |\n"
            "|------|------|------|\n"
            f"| 1 | `tts_config` | 选择模型 `{requested_model}` |\n"
            f"| 2 | `tts_synthesize` | 文本=`{text}` |\n"
            f"| 3 | `audio_encode` | 输出=`{audio_url}` |\n\n"
            "---\n\n"
            "### 合成参数\n\n"
            "| 参数 | 值 |\n"
            "|------|------|\n"
            f"| 文本内容 | {text} |\n"
            f"| 音色类型 | {voice_label} |\n"
            f"| 语速 | {speed:.1f}x |\n"
            f"| 输出来源 | {source} |\n\n"
            "---\n\n"
            "### 生成结果\n\n"
            f"- 音频地址：{audio_url}\n"
            f"- 预计时长：{duration:.1f} 秒\n"
            f"- 当前模型：{tts_model}\n"
        )

    def _render_image_result(self, *, requested_model: str, image_model: str, prompt: str, style: str, size: str, source: str, image_url: str, format_name: str) -> str:
        return (
            f"已使用图片生成工具处理请求。\n\n"
            "---\n\n"
            "## 图片生成请求\n\n"
            "### ReAct 执行流程\n\n"
            "| 步骤 | 动作 | 参数 |\n"
            "|------|------|------|\n"
            f"| 1 | `image_config` | 选择模型 `{requested_model}` |\n"
            f"| 2 | `image_generate` | 提示词=`{prompt}` |\n"
            f"| 3 | `asset_persist` | 输出=`{image_url}` |\n\n"
            "---\n\n"
            "### 生成参数\n\n"
            "| 参数 | 值 |\n"
            "|------|------|\n"
            f"| 提示词 | {prompt} |\n"
            f"| 风格 | {style} |\n"
            f"| 尺寸 | {size} |\n"
            f"| 输出来源 | {source} |\n"
            f"| 格式 | {format_name} |\n\n"
            "---\n\n"
            "### 生成结果\n\n"
            f"- 图片地址：{image_url}\n"
            f"- 当前模型：{image_model}\n"
        )

    def _select_tools(self, prompt: str, generation_target: str) -> list[tuple[str, dict, callable]]:
        lowered = prompt.lower()
        selected: list[tuple[str, dict, callable]] = []
        allowed_tools = set(self.TARGET_TOOL_IDS.get(generation_target, []))
        if "web_search" in allowed_tools and any(keyword in lowered for keyword in ["搜索", "联网", "趋势", "search"]):
            selected.append(("web_search", {"query": prompt}, web_search_tool))
        if "database_query" in allowed_tools and any(keyword in lowered for keyword in ["sql", "数据库", "销售", "订单", "query"]):
            planned_query = build_database_sql_from_prompt(prompt)
            if planned_query.get("status") == "success":
                selected.append(
                    (
                        "database_query",
                        {"sql": planned_query["sql"]},
                        database_query_tool,
                    )
                )
        if "code_interpreter" in allowed_tools and any(keyword in lowered for keyword in ["代码", "fastapi", "python", "接口"]):
            selected.append(("code_interpreter", {"task": prompt}, code_interpreter_tool))
        if "api_caller" in allowed_tools and any(keyword in lowered for keyword in ["api", "http"]):
            selected.append(("api_caller", {"url": "https://example.com", "method": "GET"}, api_caller_tool))
        if "file_manager" in allowed_tools and any(keyword in lowered for keyword in ["文件", "导出", "markdown"]):
            selected.append(("file_manager", {"action": "list", "path": "."}, file_manager_tool))
        return selected

    async def run(self, conversation_id, content: Any, model: str, generation_target: str) -> Message:
        started = time.perf_counter()
        prompt = json.dumps(content, ensure_ascii=False) if not isinstance(content, str) else content
        if self._is_tts_target(generation_target):
            tts_model = self.resolve_model_for_target(generation_target)
            text = self._extract_tts_text(prompt)
            voice, voice_label, speed = self._resolve_voice(prompt)
            tts_result = await synthesize_tts(TTSRequest(input=text, model=tts_model, voice=voice, speed=speed))
            latency = int((time.perf_counter() - started) * 1000)
            return Message(
                role="assistant",
                content=self._render_tts_result(
                    requested_model=model,
                    tts_model=tts_model,
                    text=text,
                    voice_label=voice_label,
                    speed=speed,
                    duration=tts_result.duration,
                    source=tts_result.source,
                    audio_url=tts_result.audio_url,
                ),
                model=tts_model,
                tokens_used=max(120, len(text) * 2),
                latency_ms=latency,
                thought=f"动作：识别 {self.describe_target(generation_target)} -> 调用 {tts_model} -> 生成音频文件。",
                tool_calls=[
                    ToolCall(
                        tool_id="mimo_tts",
                        display_name="MiMo TTS",
                        arguments={"input": text, "voice": voice, "model": tts_model, "speed": speed},
                        result={"status": tts_result.status, "audio_url": tts_result.audio_url, "duration": tts_result.duration, "source": tts_result.source},
                        duration_ms=latency,
                        status=tts_result.status,
                    )
                ],
                tts_audio_url=tts_result.audio_url,
            )

        if self._is_image_target(generation_target):
            image_model = self.resolve_model_for_target(generation_target)
            image_result = await image_generation_tool(prompt=prompt, style=None, size="1024x1024")
            latency = int((time.perf_counter() - started) * 1000)
            image_url = image_result.get("image_url", "")
            format_name = image_result.get("format", "png")
            source = image_result.get("source", "stub")
            return Message(
                role="assistant",
                content=self._render_image_result(
                    requested_model=model,
                    image_model=image_model,
                    prompt=prompt,
                    style=image_result.get("style", "default"),
                    size=image_result.get("size", "1024x1024"),
                    source=source,
                    image_url=image_url,
                    format_name=format_name,
                ),
                model=image_model,
                tokens_used=max(100, len(prompt) * 2),
                latency_ms=latency,
                thought=f"动作：识别 {self.describe_target(generation_target)} -> 调用图片生成工具 -> 返回可访问的图片资源。",
                tool_calls=[
                    ToolCall(
                        tool_id="image_generation",
                        display_name="Image Generation",
                        arguments={"prompt": prompt, "style": None, "size": "1024x1024"},
                        result=image_result,
                        duration_ms=latency,
                        status="failed" if image_result.get("status") == "failed" else "success",
                    )
                ],
                tts_audio_url=None,
            )

        model = self.resolve_model_for_target(generation_target)
        selected_tools = self._select_tools(prompt, generation_target)
        raw_results = await run_tools_in_parallel(selected_tools) if selected_tools else []
        tool_calls: list[ToolCall] = []
        for item in raw_results:
            tool_calls.append(
                ToolCall(
                    tool_id=item["tool_id"],
                    display_name=item["tool_id"].replace("_", " ").title(),
                    arguments=item["arguments"],
                    result=item["result"],
                    duration_ms=20,
                    status="failed" if item["result"].get("status") == "failed" else "success",
                )
            )

        conversation = store.get_conversation(conversation_id)
        response = await provider.complete(
            model=model,
            messages=[
                {"role": "system", "content": conversation.system_prompt},
                *[{"role": message.role, "content": str(message.content)} for message in conversation.messages[-8:]],
                {"role": "user", "content": prompt},
            ],
            tools_used=raw_results,
        )
        latency = int((time.perf_counter() - started) * 1000)
        return Message(
            role="assistant",
            content=response["content"],
            model=model,
            tokens_used=response.get("tokens_used", 0),
            latency_ms=latency,
            thought=f"动作：识别 {self.describe_target(generation_target)} -> 调用 {model} -> 汇总结果。" if response.get("thought") else None,
            tool_calls=tool_calls,
            tts_audio_url=None,
        )


agent_engine = AgentEngine()