from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str = Field(default_factory=lambda: f"tool_{uuid4().hex[:12]}")
    tool_id: str
    display_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    duration_ms: int
    status: Literal["success", "failed"] = "success"


class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    role: Role
    content: Any
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model: str | None = None
    tokens_used: int = 0
    latency_ms: int = 0
    thought: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tts_audio_url: str | None = None


class Conversation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    system_prompt: str
    model: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str | None = None
    messages: list[Message] = Field(default_factory=list)


class ConversationCreate(BaseModel):
    title: str = "新会话"
    system_prompt: str = "你是 Agent Core 智能体平台中的企业级智能助手。"
    default_model: str | None = None


class ConversationUpdate(BaseModel):
    title: str


class ConversationListItem(BaseModel):
    id: UUID
    title: str
    model: str
    created_at: datetime
    updated_at: datetime
    preview: str | None = None


class PaginatedConversations(BaseModel):
    items: list[ConversationListItem]
    total: int
    page: int
    page_size: int


class MessageCreate(BaseModel):
    content: Any
    model: str | None = None
    generation_target: str | None = None
    stream: bool = False


class MessageResponse(BaseModel):
    conversation_id: UUID
    message: Message


class AgentConfig(BaseModel):
    model: str
    temperature: float = 0.3
    max_iterations: int = 10
    memory_window: int = 20
    mimo_fallback: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)


class AgentConfigUpdate(BaseModel):
    model: str | None = None
    temperature: float | None = None
    max_iterations: int | None = None
    memory_window: int | None = None
    mimo_fallback: list[str] | None = None
    enabled_tools: list[str] | None = None


class ToolDefinition(BaseModel):
    id: str
    name: str
    description: str
    parameters_schema: dict[str, Any]
    support_models: list[str]
    enabled: bool = True


class DatabaseQueryRequest(BaseModel):
    sql: str


class DatabaseQueryResponse(BaseModel):
    status: Literal["success", "failed"]
    sql: str | None = None
    row_count: int = 0
    truncated: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    detail: str | None = None


class DatabaseSchemaColumn(BaseModel):
    name: str
    data_type: str


class DatabaseSchemaTable(BaseModel):
    name: str
    columns: list[DatabaseSchemaColumn] = Field(default_factory=list)


class DatabaseSchemaResponse(BaseModel):
    status: Literal["success", "failed"]
    dialect: str | None = None
    tables: list[DatabaseSchemaTable] = Field(default_factory=list)
    error: str | None = None


class TTSRequest(BaseModel):
    model: str = "MiMo-V2.5-TTS"
    input: str
    voice: str = "default-female"
    speed: float = 1.0


class TTSResponse(BaseModel):
    model: str
    audio_url: str
    duration: float
    source: str = "stub"
    status: Literal["success", "failed"] = "success"
