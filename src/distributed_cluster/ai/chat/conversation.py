"""
Conversation Management - إدارة المحادثات
==========================================

Manages chat conversations with history, context, and persistence.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from distributed_cluster.ai.llm.provider import (
    GenerationConfig,
    LLMProvider,
)

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """دور المرسل."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """رسالة في المحادثة."""

    role: MessageRole
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Metadata
    model: Optional[str] = None
    tokens: int = 0
    generation_time_ms: float = 0

    # Tool-related
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None

    # Attachments
    attachments: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "role": self.role.value,
            "content": self.content,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "tokens": self.tokens,
        }

    def to_llm_format(self) -> Dict[str, str]:
        """تحويل لصيغة LLM."""
        return {
            "role": self.role.value,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """إنشاء من قاموس."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            message_id=data.get("message_id", str(uuid.uuid4())),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            model=data.get("model"),
            tokens=data.get("tokens", 0),
        )


@dataclass
class Conversation:
    """محادثة كاملة."""

    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # Settings
    system_prompt: Optional[str] = None
    model: str = "llama3.2"
    max_context_messages: int = 50

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # Stats
    total_tokens: int = 0
    message_count: int = 0

    def add_message(self, message: Message) -> None:
        """إضافة رسالة."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        self.message_count += 1
        self.total_tokens += message.tokens

        # Auto-generate title from first user message
        if not self.title and message.role == MessageRole.USER:
            self.title = message.content[:50] + "..." if len(message.content) > 50 else message.content

    def add_user_message(self, content: str) -> Message:
        """إضافة رسالة مستخدم."""
        message = Message(role=MessageRole.USER, content=content)
        self.add_message(message)
        return message

    def add_assistant_message(
        self,
        content: str,
        model: Optional[str] = None,
        tokens: int = 0,
        generation_time_ms: float = 0,
    ) -> Message:
        """إضافة رسالة مساعد."""
        message = Message(
            role=MessageRole.ASSISTANT,
            content=content,
            model=model or self.model,
            tokens=tokens,
            generation_time_ms=generation_time_ms,
        )
        self.add_message(message)
        return message

    def add_system_message(self, content: str) -> Message:
        """إضافة رسالة نظام."""
        message = Message(role=MessageRole.SYSTEM, content=content)
        self.add_message(message)
        return message

    def get_context_messages(self) -> List[Dict[str, str]]:
        """الحصول على رسائل السياق لـ LLM."""
        messages = []

        # Add system prompt
        if self.system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": self.system_prompt,
                }
            )

        # Add recent messages
        recent = self.messages[-self.max_context_messages :]
        for msg in recent:
            messages.append(msg.to_llm_format())

        return messages

    def clear(self) -> None:
        """مسح المحادثة."""
        self.messages.clear()
        self.total_tokens = 0
        self.message_count = 0
        self.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "system_prompt": self.system_prompt,
            "model": self.model,
            "metadata": self.metadata,
            "tags": self.tags,
            "total_tokens": self.total_tokens,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Conversation:
        """إنشاء من قاموس."""
        conv = cls(
            conversation_id=data.get("conversation_id", str(uuid.uuid4())),
            title=data.get("title"),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow(),
            system_prompt=data.get("system_prompt"),
            model=data.get("model", "llama3.2"),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            total_tokens=data.get("total_tokens", 0),
            message_count=data.get("message_count", 0),
        )

        for msg_data in data.get("messages", []):
            conv.messages.append(Message.from_dict(msg_data))

        return conv

    def save(self, path: Path) -> None:
        """حفظ المحادثة."""
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> Conversation:
        """تحميل محادثة."""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


class ConversationManager:
    """
    مدير المحادثات.

    Manages multiple conversations with persistence and retrieval.
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        llm_provider: Optional[LLMProvider] = None,
        default_model: str = "llama3.2",
        default_system_prompt: Optional[str] = None,
    ):
        self.storage_dir = storage_dir or Path.home() / ".theend" / "conversations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.llm_provider = llm_provider
        self.default_model = default_model
        self.default_system_prompt = default_system_prompt or (
            "You are a helpful AI assistant. " "Respond concisely and helpfully."
        )

        # Active conversations
        self._conversations: Dict[str, Conversation] = {}

    def create_conversation(
        self,
        title: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Conversation:
        """إنشاء محادثة جديدة."""
        conv = Conversation(
            title=title,
            system_prompt=system_prompt or self.default_system_prompt,
            model=model or self.default_model,
        )

        self._conversations[conv.conversation_id] = conv

        logger.info(f"Created conversation: {conv.conversation_id}")

        return conv

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """الحصول على محادثة."""
        # Check memory first
        if conversation_id in self._conversations:
            return self._conversations[conversation_id]

        # Try loading from disk
        path = self.storage_dir / f"{conversation_id}.json"
        if path.exists():
            conv = Conversation.load(path)
            self._conversations[conversation_id] = conv
            return conv

        return None

    def list_conversations(
        self,
        limit: int = 50,
        tag: Optional[str] = None,
    ) -> List[Conversation]:
        """قائمة المحادثات."""
        # Load all from storage
        conversations = []

        for path in self.storage_dir.glob("*.json"):
            try:
                conv = Conversation.load(path)
                if tag and tag not in conv.tags:
                    continue
                conversations.append(conv)
            except Exception as e:
                logger.warning(f"Failed to load conversation {path}: {e}")

        # Sort by updated_at
        conversations.sort(key=lambda c: c.updated_at, reverse=True)

        return conversations[:limit]

    def save_conversation(self, conversation: Conversation) -> None:
        """حفظ محادثة."""
        path = self.storage_dir / f"{conversation.conversation_id}.json"
        conversation.save(path)
        logger.debug(f"Saved conversation: {conversation.conversation_id}")

    def delete_conversation(self, conversation_id: str) -> bool:
        """حذف محادثة."""
        # Remove from memory
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]

        # Remove from disk
        path = self.storage_dir / f"{conversation_id}.json"
        if path.exists():
            path.unlink()
            logger.info(f"Deleted conversation: {conversation_id}")
            return True

        return False

    async def chat(
        self,
        conversation: Conversation,
        user_message: str,
        config: Optional[GenerationConfig] = None,
    ) -> Message:
        """إرسال رسالة والحصول على رد."""
        if not self.llm_provider:
            raise ValueError("LLM provider not configured")

        # Add user message
        conversation.add_user_message(user_message)

        # Get context
        messages = conversation.get_context_messages()

        # Generate response
        config = config or GenerationConfig()
        response = await self.llm_provider.chat(
            messages=messages,
            model=conversation.model,
            config=config,
        )

        # Add assistant message
        assistant_msg = conversation.add_assistant_message(
            content=response.text,
            model=response.model,
            tokens=response.total_tokens,
            generation_time_ms=response.generation_time_ms,
        )

        # Auto-save
        self.save_conversation(conversation)

        return assistant_msg

    async def chat_stream(
        self,
        conversation: Conversation,
        user_message: str,
        config: Optional[GenerationConfig] = None,
    ) -> AsyncIterator[str]:
        """إرسال رسالة مع streaming."""
        if not self.llm_provider:
            raise ValueError("LLM provider not configured")

        # Add user message
        conversation.add_user_message(user_message)

        # Get context
        messages = conversation.get_context_messages()

        # Generate response with streaming
        config = config or GenerationConfig(stream=True)

        full_response = []

        # Check if provider supports chat_stream
        if hasattr(self.llm_provider, "chat_stream"):
            async for chunk in self.llm_provider.chat_stream(
                messages=messages,
                model=conversation.model,
                config=config,
            ):
                full_response.append(chunk)
                yield chunk
        else:
            # Fallback to non-streaming
            response = await self.llm_provider.chat(
                messages=messages,
                model=conversation.model,
                config=config,
            )
            full_response.append(response.text)
            yield response.text

        # Add complete response
        conversation.add_assistant_message(
            content="".join(full_response),
            model=conversation.model,
        )

        # Auto-save
        self.save_conversation(conversation)

    def search_conversations(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Conversation]:
        """البحث في المحادثات."""
        results = []
        query_lower = query.lower()

        for path in self.storage_dir.glob("*.json"):
            try:
                conv = Conversation.load(path)

                # Search in title
                if conv.title and query_lower in conv.title.lower():
                    results.append(conv)
                    continue

                # Search in messages
                for msg in conv.messages:
                    if query_lower in msg.content.lower():
                        results.append(conv)
                        break

            except Exception:
                continue

        return results[:limit]

    def export_conversation(
        self,
        conversation: Conversation,
        format: str = "markdown",
    ) -> str:
        """تصدير محادثة."""
        if format == "markdown":
            lines = [f"# {conversation.title or 'Untitled Conversation'}"]
            lines.append(f"\n*Created: {conversation.created_at.isoformat()}*\n")

            for msg in conversation.messages:
                role = msg.role.value.capitalize()
                lines.append(f"## {role}")
                lines.append(msg.content)
                lines.append("")

            return "\n".join(lines)

        elif format == "json":
            return json.dumps(conversation.to_dict(), ensure_ascii=False, indent=2)

        else:
            raise ValueError(f"Unknown format: {format}")
