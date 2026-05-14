from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import datetime
from math import ceil
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from redis import Redis
from sqlalchemy import DateTime, Integer, MetaData, String, Table, Text, create_engine, delete, func, insert, select, update
from sqlalchemy.engine import Connection, Engine, RowMapping

from app.core.config import settings
from app.core.schemas import AgentConfig, Conversation, ConversationListItem, Message, ToolCall


logger = logging.getLogger(__name__)


DEFAULT_ENABLED_TOOLS = [
    "web_search",
    "code_interpreter",
    "database_query",
    "api_caller",
    "file_manager",
    "mimo_tts",
]


def default_agent_config() -> AgentConfig:
    return AgentConfig(
        model=settings.default_model,
        temperature=0.3,
        max_iterations=settings.max_iterations,
        memory_window=settings.memory_window,
        mimo_fallback=settings.mimo_fallback,
        enabled_tools=DEFAULT_ENABLED_TOOLS,
    )


class InMemoryStore:
    def __init__(self) -> None:
        self._conversations: OrderedDict[UUID, Conversation] = OrderedDict()
        self._agent_config = default_agent_config()

    def create_conversation(self, conversation: Conversation) -> Conversation:
        self._conversations[conversation.id] = conversation
        return conversation

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return conversation

    def list_conversations(self, page: int, page_size: int) -> dict[str, Any]:
        ordered = list(reversed(self._conversations.values()))
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            ConversationListItem(
                id=conversation.id,
                title=conversation.title,
                model=conversation.model,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                preview=self._preview(conversation.messages[-1].content) if conversation.messages else None,
            )
            for conversation in ordered[start:end]
        ]
        return {
            "items": items,
            "total": len(ordered),
            "page": page,
            "page_size": page_size,
            "pages": ceil(len(ordered) / page_size) if page_size else 1,
        }

    def rename_conversation(self, conversation_id: UUID, title: str) -> Conversation:
        conversation = self.get_conversation(conversation_id)
        conversation.title = title
        conversation.updated_at = datetime.utcnow()
        return conversation

    def delete_conversation(self, conversation_id: UUID) -> None:
        self.get_conversation(conversation_id)
        self._conversations.pop(conversation_id, None)

    def append_message(self, conversation_id: UUID, message: Message) -> Message:
        conversation = self.get_conversation(conversation_id)
        conversation.messages.append(message)
        conversation.updated_at = datetime.utcnow()
        self._compress_history(conversation)
        return message

    def export_conversation(self, conversation_id: UUID, fmt: str) -> str | dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        if fmt == "json":
            return conversation.model_dump(mode="json")
        lines = [f"# {conversation.title}", "", f"Model: {conversation.model}", ""]
        if conversation.summary:
            lines.extend(["## Summary", conversation.summary, ""])
        for message in conversation.messages:
            lines.extend([f"## {message.role}", str(message.content), ""])
            if message.tts_audio_url:
                lines.extend([f"Audio: {message.tts_audio_url}", ""])
        return "\n".join(lines)

    def get_agent_config(self) -> AgentConfig:
        return self._agent_config

    def update_agent_config(self, payload: dict[str, Any]) -> AgentConfig:
        current = self._agent_config.model_dump()
        current.update({key: value for key, value in payload.items() if value is not None})
        self._agent_config = AgentConfig(**current)
        return self._agent_config

    @staticmethod
    def _preview(content: Any) -> str:
        text = str(content)
        return text[:80] + ("..." if len(text) > 80 else "")

    def _compress_history(self, conversation: Conversation) -> None:
        max_messages = max(self._agent_config.memory_window * 2, 4)
        if len(conversation.messages) <= max_messages:
            return
        removed = conversation.messages[:-max_messages]
        conversation.messages = conversation.messages[-max_messages:]
        summary_lines = []
        for message in removed[-6:]:
            summary_lines.append(f"{message.role}: {self._preview(message.content)}")
        summary_block = " | ".join(summary_lines)
        if conversation.summary:
            conversation.summary = f"{conversation.summary} || {summary_block}"[:1000]
        else:
            conversation.summary = summary_block[:1000]


class PersistentStore:
    def __init__(self) -> None:
        self._metadata = MetaData()
        self._engine = create_engine(self._normalize_database_url(settings.database_url), pool_pre_ping=True)
        self._redis = self._build_redis_client()
        self._config_cache_key = "agent-core:agent-config"
        self._conversations = Table(
            "conversations",
            self._metadata,
            StringColumn("id", 36, primary_key=True),
            StringColumn("title", 255, nullable=False),
            TextColumn("system_prompt", nullable=False),
            StringColumn("model", 120, nullable=False),
            TextColumn("summary"),
            DateTimeColumn("created_at", nullable=False),
            DateTimeColumn("updated_at", nullable=False),
        )
        self._messages = Table(
            "messages",
            self._metadata,
            StringColumn("id", 36, primary_key=True),
            StringColumn("conversation_id", 36, nullable=False, index=True),
            StringColumn("role", 32, nullable=False),
            TextColumn("content_json", nullable=False),
            StringColumn("model", 120),
            IntegerColumn("tokens_used", nullable=False, default=0),
            IntegerColumn("latency_ms", nullable=False, default=0),
            TextColumn("thought"),
            TextColumn("tool_calls_json", nullable=False),
            TextColumn("tts_audio_url"),
            DateTimeColumn("created_at", nullable=False),
        )
        self._agent_configs = Table(
            "agent_configs",
            self._metadata,
            StringColumn("config_key", 80, primary_key=True),
            TextColumn("payload_json", nullable=False),
            DateTimeColumn("updated_at", nullable=False),
        )

    def initialize(self) -> None:
        self._metadata.create_all(self._engine)
        self.get_agent_config()

    def create_conversation(self, conversation: Conversation) -> Conversation:
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._conversations).values(
                    id=str(conversation.id),
                    title=conversation.title,
                    system_prompt=conversation.system_prompt,
                    model=conversation.model,
                    summary=conversation.summary,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )
        return conversation

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._conversations).where(self._conversations.c.id == str(conversation_id))
            ).mappings().first()
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            message_rows = connection.execute(
                select(self._messages)
                .where(self._messages.c.conversation_id == str(conversation_id))
                .order_by(self._messages.c.created_at.asc(), self._messages.c.id.asc())
            ).mappings().all()
        return self._conversation_from_rows(row, message_rows)

    def list_conversations(self, page: int, page_size: int) -> dict[str, Any]:
        offset = max(page - 1, 0) * page_size
        with self._engine.begin() as connection:
            total = connection.execute(select(func.count()).select_from(self._conversations)).scalar_one()
            rows = connection.execute(
                select(self._conversations)
                .order_by(self._conversations.c.updated_at.desc())
                .offset(offset)
                .limit(page_size)
            ).mappings().all()

            items = []
            for row in rows:
                preview_row = connection.execute(
                    select(self._messages.c.content_json)
                    .where(self._messages.c.conversation_id == row["id"])
                    .order_by(self._messages.c.created_at.desc(), self._messages.c.id.desc())
                    .limit(1)
                ).first()
                preview = None
                if preview_row is not None:
                    preview = self._preview(self._from_json(preview_row[0]))
                items.append(
                    ConversationListItem(
                        id=UUID(row["id"]),
                        title=row["title"],
                        model=row["model"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        preview=preview,
                    )
                )
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": ceil(total / page_size) if page_size else 1,
        }

    def rename_conversation(self, conversation_id: UUID, title: str) -> Conversation:
        updated_at = datetime.utcnow()
        with self._engine.begin() as connection:
            result = connection.execute(
                update(self._conversations)
                .where(self._conversations.c.id == str(conversation_id))
                .values(title=title, updated_at=updated_at)
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: UUID) -> None:
        with self._engine.begin() as connection:
            connection.execute(delete(self._messages).where(self._messages.c.conversation_id == str(conversation_id)))
            result = connection.execute(delete(self._conversations).where(self._conversations.c.id == str(conversation_id)))
            if result.rowcount == 0:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    def append_message(self, conversation_id: UUID, message: Message) -> Message:
        with self._engine.begin() as connection:
            exists = connection.execute(
                select(self._conversations.c.id).where(self._conversations.c.id == str(conversation_id))
            ).first()
            if exists is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            connection.execute(
                insert(self._messages).values(
                    id=str(message.id),
                    conversation_id=str(conversation_id),
                    role=message.role,
                    content_json=self._to_json(message.content),
                    model=message.model,
                    tokens_used=message.tokens_used,
                    latency_ms=message.latency_ms,
                    thought=message.thought,
                    tool_calls_json=self._to_json([tool.model_dump(mode="json") for tool in message.tool_calls]),
                    tts_audio_url=message.tts_audio_url,
                    created_at=message.created_at,
                )
            )
            connection.execute(
                update(self._conversations)
                .where(self._conversations.c.id == str(conversation_id))
                .values(updated_at=datetime.utcnow())
            )
            self._compress_history(connection, conversation_id)
        return message

    def export_conversation(self, conversation_id: UUID, fmt: str) -> str | dict[str, Any]:
        conversation = self.get_conversation(conversation_id)
        if fmt == "json":
            return conversation.model_dump(mode="json")
        lines = [f"# {conversation.title}", "", f"Model: {conversation.model}", ""]
        if conversation.summary:
            lines.extend(["## Summary", conversation.summary, ""])
        for message in conversation.messages:
            lines.extend([f"## {message.role}", str(message.content), ""])
            if message.tts_audio_url:
                lines.extend([f"Audio: {message.tts_audio_url}", ""])
        return "\n".join(lines)

    def get_agent_config(self) -> AgentConfig:
        cached = self._redis_get(self._config_cache_key)
        if cached:
            return AgentConfig(**json.loads(cached))

        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._agent_configs).where(self._agent_configs.c.config_key == "default")
            ).mappings().first()
            if row is None:
                config = default_agent_config()
                connection.execute(
                    insert(self._agent_configs).values(
                        config_key="default",
                        payload_json=json.dumps(config.model_dump(mode="json"), ensure_ascii=False),
                        updated_at=datetime.utcnow(),
                    )
                )
            else:
                config = AgentConfig(**json.loads(row["payload_json"]))

        self._redis_set(self._config_cache_key, json.dumps(config.model_dump(mode="json"), ensure_ascii=False))
        return config

    def update_agent_config(self, payload: dict[str, Any]) -> AgentConfig:
        current = self.get_agent_config().model_dump()
        current.update({key: value for key, value in payload.items() if value is not None})
        config = AgentConfig(**current)
        serialized = json.dumps(config.model_dump(mode="json"), ensure_ascii=False)

        with self._engine.begin() as connection:
            existing = connection.execute(
                select(self._agent_configs.c.config_key).where(self._agent_configs.c.config_key == "default")
            ).first()
            if existing is None:
                connection.execute(
                    insert(self._agent_configs).values(
                        config_key="default",
                        payload_json=serialized,
                        updated_at=datetime.utcnow(),
                    )
                )
            else:
                connection.execute(
                    update(self._agent_configs)
                    .where(self._agent_configs.c.config_key == "default")
                    .values(payload_json=serialized, updated_at=datetime.utcnow())
                )

        self._redis_set(self._config_cache_key, serialized)
        return config

    @staticmethod
    def _normalize_database_url(url: str | None) -> str:
        if not url:
            raise ValueError("DATABASE_URL is required for persistent storage")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        return url

    def _build_redis_client(self) -> Redis | None:
        if not settings.redis_host:
            return None
        client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            db=settings.redis_db,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        try:
            client.ping()
        except Exception:
            logger.exception("Redis is configured but unavailable. Falling back to database-only config storage.")
            return None
        return client

    def _redis_get(self, key: str) -> str | None:
        if self._redis is None:
            return None
        try:
            return self._redis.get(key)
        except Exception:
            logger.exception("Failed to read agent config from Redis cache.")
            return None

    def _redis_set(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.set(key, value)
        except Exception:
            logger.exception("Failed to write agent config to Redis cache.")

    def _compress_history(self, connection: Connection, conversation_id: UUID) -> None:
        config = self.get_agent_config()
        max_messages = max(config.memory_window * 2, 4)
        rows = connection.execute(
            select(self._messages)
            .where(self._messages.c.conversation_id == str(conversation_id))
            .order_by(self._messages.c.created_at.asc(), self._messages.c.id.asc())
        ).mappings().all()
        if len(rows) <= max_messages:
            return

        removed = rows[:-max_messages]
        keep_ids = [row["id"] for row in rows[-max_messages:]]
        removed_ids = [row["id"] for row in removed]
        summary_lines = [
            f"{row['role']}: {self._preview(self._from_json(row['content_json']))}"
            for row in removed[-6:]
        ]
        summary_block = " | ".join(summary_lines)[:1000]
        current_summary = connection.execute(
            select(self._conversations.c.summary).where(self._conversations.c.id == str(conversation_id))
        ).scalar_one()
        merged_summary = f"{current_summary} || {summary_block}"[:1000] if current_summary else summary_block
        connection.execute(delete(self._messages).where(self._messages.c.id.in_(removed_ids)))
        connection.execute(
            update(self._conversations)
            .where(self._conversations.c.id == str(conversation_id))
            .values(summary=merged_summary)
        )

    def _conversation_from_rows(self, conversation_row: RowMapping, message_rows: list[RowMapping]) -> Conversation:
        messages = [self._message_from_row(row) for row in message_rows]
        return Conversation(
            id=UUID(conversation_row["id"]),
            title=conversation_row["title"],
            system_prompt=conversation_row["system_prompt"],
            model=conversation_row["model"],
            created_at=conversation_row["created_at"],
            updated_at=conversation_row["updated_at"],
            summary=conversation_row["summary"],
            messages=messages,
        )

    def _message_from_row(self, row: RowMapping) -> Message:
        tool_calls_payload = self._from_json(row["tool_calls_json"])
        return Message(
            id=UUID(row["id"]),
            role=row["role"],
            content=self._from_json(row["content_json"]),
            created_at=row["created_at"],
            model=row["model"],
            tokens_used=row["tokens_used"],
            latency_ms=row["latency_ms"],
            thought=row["thought"],
            tool_calls=[ToolCall(**tool_call) for tool_call in tool_calls_payload],
            tts_audio_url=row["tts_audio_url"],
        )

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _from_json(value: str) -> Any:
        return json.loads(value)

    @staticmethod
    def _preview(content: Any) -> str:
        text = str(content)
        return text[:80] + ("..." if len(text) > 80 else "")


def StringColumn(name: str, length: int, primary_key: bool = False, nullable: bool = True, index: bool = False):
    return TableColumn(String(length), name, primary_key=primary_key, nullable=nullable, index=index)


def TextColumn(name: str, nullable: bool = True):
    return TableColumn(Text(), name, nullable=nullable)


def IntegerColumn(name: str, nullable: bool = True, default: int | None = None):
    return TableColumn(Integer(), name, nullable=nullable, default=default)


def DateTimeColumn(name: str, nullable: bool = True):
    return TableColumn(DateTime(), name, nullable=nullable)


def TableColumn(column_type, name: str, **kwargs):
    from sqlalchemy import Column

    return Column(name, column_type, **kwargs)


class StoreFacade:
    def __init__(self) -> None:
        self._backend: InMemoryStore | PersistentStore = InMemoryStore()
        self.backend_name = "memory"
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        if settings.database_url:
            try:
                backend = PersistentStore()
                backend.initialize()
                self._backend = backend
                self.backend_name = "postgresql"
            except Exception:
                logger.exception("Failed to initialize persistent storage. Falling back to in-memory store.")
        self._initialized = True

    def create_conversation(self, conversation: Conversation) -> Conversation:
        return self._backend.create_conversation(conversation)

    def get_conversation(self, conversation_id: UUID) -> Conversation:
        return self._backend.get_conversation(conversation_id)

    def list_conversations(self, page: int, page_size: int) -> dict[str, Any]:
        return self._backend.list_conversations(page, page_size)

    def rename_conversation(self, conversation_id: UUID, title: str) -> Conversation:
        return self._backend.rename_conversation(conversation_id, title)

    def delete_conversation(self, conversation_id: UUID) -> None:
        self._backend.delete_conversation(conversation_id)

    def append_message(self, conversation_id: UUID, message: Message) -> Message:
        return self._backend.append_message(conversation_id, message)

    def export_conversation(self, conversation_id: UUID, fmt: str) -> str | dict[str, Any]:
        return self._backend.export_conversation(conversation_id, fmt)

    def get_agent_config(self) -> AgentConfig:
        return self._backend.get_agent_config()

    def update_agent_config(self, payload: dict[str, Any]) -> AgentConfig:
        return self._backend.update_agent_config(payload)


store = StoreFacade()