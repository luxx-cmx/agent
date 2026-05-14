from __future__ import annotations

import json
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import require_auth
from app.core.config import settings
from app.core.schemas import (
    Conversation,
    ConversationCreate,
    ConversationUpdate,
    Message,
    MessageCreate,
    MessageResponse,
    PaginatedConversations,
)
from app.services.agent_engine import agent_engine
from app.services.store import store


router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_auth)])


@router.get("", response_model=PaginatedConversations)
async def list_conversations(page: int = 1, page_size: int = 10) -> PaginatedConversations:
    payload = store.list_conversations(page=page, page_size=page_size)
    return PaginatedConversations(**payload)


@router.post("", response_model=Conversation)
async def create_conversation(payload: ConversationCreate) -> Conversation:
    conversation = Conversation(
        title=payload.title,
        system_prompt=payload.system_prompt,
        model=payload.default_model or settings.default_model,
    )
    return store.create_conversation(conversation)


@router.get("/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: UUID) -> Conversation:
    return store.get_conversation(conversation_id)


@router.patch("/{conversation_id}", response_model=Conversation)
async def rename_conversation(conversation_id: UUID, payload: ConversationUpdate) -> Conversation:
    return store.rename_conversation(conversation_id, payload.title)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID) -> Response:
    store.delete_conversation(conversation_id)
    return Response(status_code=204)


@router.get("/{conversation_id}/export")
async def export_conversation(conversation_id: UUID, format: str = "markdown"):
    fmt = "json" if format.lower() == "json" else "markdown"
    exported = store.export_conversation(conversation_id, fmt)
    if fmt == "json":
        return JSONResponse(exported)
    return Response(content=exported, media_type="text/markdown")


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_reply(conversation_id: UUID, user_message: Message, model: str, generation_target: str) -> AsyncIterator[str]:
    target = generation_target or "auto"
    yield _sse_event("agent/thought", {"content": f"动作：识别 {agent_engine.describe_target(target)} -> 选择对应模型与工具。"})
    response = await agent_engine.run(conversation_id, user_message.content, model, target)
    if response.tool_calls:
        for tool in response.tool_calls:
            yield _sse_event(
                "tool_call",
                {
                    "tool_id": tool.tool_id,
                    "arguments": tool.arguments,
                    "result": tool.result,
                    "duration_ms": tool.duration_ms,
                },
            )
    stored = store.append_message(conversation_id, response)
    if stored.tts_audio_url:
        yield _sse_event("tts_progress", {"status": "completed", "audio_url": stored.tts_audio_url})
    yield _sse_event(
        "final_answer",
        {
            "conversation_id": str(conversation_id),
            "message": stored.model_dump(mode="json"),
        },
    )


@router.post("/{conversation_id}/messages")
async def create_message(conversation_id: UUID, payload: MessageCreate):
    conversation = store.get_conversation(conversation_id)
    generation_target = payload.generation_target or "auto"
    resolved_target = agent_engine.resolve_generation_target(str(payload.content), generation_target)
    resolved_model = agent_engine.resolve_model_for_target(resolved_target)
    user_message = Message(role="user", content=payload.content, model=resolved_model)
    store.append_message(conversation_id, user_message)
    if payload.stream:
        return StreamingResponse(_stream_reply(conversation_id, user_message, resolved_model, resolved_target), media_type="text/event-stream")
    assistant_message = await agent_engine.run(conversation_id, payload.content, resolved_model, resolved_target)
    stored = store.append_message(conversation_id, assistant_message)
    return MessageResponse(conversation_id=conversation_id, message=stored)