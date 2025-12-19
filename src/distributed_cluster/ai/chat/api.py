"""
Chat API - واجهة برمجة المحادثة
================================

FastAPI-based REST API for chat functionality.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from distributed_cluster.ai.chat.conversation import (
    Conversation,
    ConversationManager,
    Message,
)
from distributed_cluster.ai.llm.provider import GenerationConfig, LLMProvider

logger = logging.getLogger(__name__)


# Request/Response Models
class CreateConversationRequest(BaseModel):
    """طلب إنشاء محادثة."""
    title: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """طلب محادثة."""
    message: str
    conversation_id: Optional[str] = None
    model: Optional[str] = None
    stream: bool = False

    # Generation settings
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 0.9


class ChatResponse(BaseModel):
    """استجابة المحادثة."""
    conversation_id: str
    message_id: str
    content: str
    model: str
    tokens: int
    generation_time_ms: float


class ConversationResponse(BaseModel):
    """استجابة المحادثة."""
    conversation_id: str
    title: Optional[str]
    message_count: int
    total_tokens: int
    created_at: str
    updated_at: str
    model: str


class MessageResponse(BaseModel):
    """استجابة رسالة."""
    message_id: str
    role: str
    content: str
    timestamp: str
    tokens: int


class ChatAPI:
    """
    واجهة برمجة المحادثة.

    Provides REST API endpoints for chat functionality.
    """

    def __init__(
        self,
        conversation_manager: ConversationManager,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.manager = conversation_manager
        self.llm_provider = llm_provider or conversation_manager.llm_provider

        # Create router
        self.router = APIRouter(prefix="/chat", tags=["chat"])
        self._setup_routes()

        # Active WebSocket connections
        self._websockets: Dict[str, List[WebSocket]] = {}

    def _setup_routes(self) -> None:
        """إعداد المسارات."""

        @self.router.post("/conversations", response_model=ConversationResponse)
        async def create_conversation(request: CreateConversationRequest):
            """إنشاء محادثة جديدة."""
            conv = self.manager.create_conversation(
                title=request.title,
                system_prompt=request.system_prompt,
                model=request.model,
            )
            conv.tags = request.tags
            self.manager.save_conversation(conv)

            return ConversationResponse(
                conversation_id=conv.conversation_id,
                title=conv.title,
                message_count=conv.message_count,
                total_tokens=conv.total_tokens,
                created_at=conv.created_at.isoformat(),
                updated_at=conv.updated_at.isoformat(),
                model=conv.model,
            )

        @self.router.get("/conversations", response_model=List[ConversationResponse])
        async def list_conversations(limit: int = 50, tag: Optional[str] = None):
            """قائمة المحادثات."""
            conversations = self.manager.list_conversations(limit=limit, tag=tag)

            return [
                ConversationResponse(
                    conversation_id=c.conversation_id,
                    title=c.title,
                    message_count=c.message_count,
                    total_tokens=c.total_tokens,
                    created_at=c.created_at.isoformat(),
                    updated_at=c.updated_at.isoformat(),
                    model=c.model,
                )
                for c in conversations
            ]

        @self.router.get("/conversations/{conversation_id}")
        async def get_conversation(conversation_id: str):
            """الحصول على محادثة."""
            conv = self.manager.get_conversation(conversation_id)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")

            return conv.to_dict()

        @self.router.delete("/conversations/{conversation_id}")
        async def delete_conversation(conversation_id: str):
            """حذف محادثة."""
            success = self.manager.delete_conversation(conversation_id)
            if not success:
                raise HTTPException(status_code=404, detail="Conversation not found")

            return {"status": "deleted", "conversation_id": conversation_id}

        @self.router.get("/conversations/{conversation_id}/messages")
        async def get_messages(
            conversation_id: str,
            limit: int = 100,
            offset: int = 0,
        ):
            """الحصول على رسائل محادثة."""
            conv = self.manager.get_conversation(conversation_id)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")

            messages = conv.messages[offset:offset + limit]

            return {
                "conversation_id": conversation_id,
                "messages": [m.to_dict() for m in messages],
                "total": len(conv.messages),
                "offset": offset,
                "limit": limit,
            }

        @self.router.post("/", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """إرسال رسالة."""
            # Get or create conversation
            if request.conversation_id:
                conv = self.manager.get_conversation(request.conversation_id)
                if not conv:
                    raise HTTPException(status_code=404, detail="Conversation not found")
            else:
                conv = self.manager.create_conversation(
                    model=request.model,
                )

            # Update model if specified
            if request.model:
                conv.model = request.model

            # Create generation config
            config = GenerationConfig(
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                top_p=request.top_p,
            )

            # Handle streaming
            if request.stream:
                return StreamingResponse(
                    self._stream_response(conv, request.message, config),
                    media_type="text/event-stream",
                )

            # Non-streaming response
            assistant_msg = await self.manager.chat(
                conversation=conv,
                user_message=request.message,
                config=config,
            )

            # Broadcast to websockets
            await self._broadcast(conv.conversation_id, assistant_msg)

            return ChatResponse(
                conversation_id=conv.conversation_id,
                message_id=assistant_msg.message_id,
                content=assistant_msg.content,
                model=assistant_msg.model or conv.model,
                tokens=assistant_msg.tokens,
                generation_time_ms=assistant_msg.generation_time_ms,
            )

        @self.router.post("/complete")
        async def complete(
            prompt: str,
            model: Optional[str] = None,
            system_prompt: Optional[str] = None,
            temperature: float = 0.7,
            max_tokens: int = 2048,
        ):
            """توليد نص بدون محادثة."""
            if not self.llm_provider:
                raise HTTPException(status_code=500, detail="LLM provider not configured")

            config = GenerationConfig(
                temperature=temperature,
                max_tokens=max_tokens,
            )

            response = await self.llm_provider.generate(
                prompt=prompt,
                model=model or self.manager.default_model,
                config=config,
                system_prompt=system_prompt,
            )

            return {
                "text": response.text,
                "model": response.model,
                "tokens": response.total_tokens,
                "generation_time_ms": response.generation_time_ms,
            }

        @self.router.get("/models")
        async def list_models():
            """قائمة النماذج المتاحة."""
            if not self.llm_provider:
                raise HTTPException(status_code=500, detail="LLM provider not configured")

            models = await self.llm_provider.list_models()

            return {
                "models": [
                    {
                        "name": m.name,
                        "provider": m.provider,
                        "size_bytes": m.size_bytes,
                        "parameter_size": m.parameter_size,
                    }
                    for m in models
                ]
            }

        @self.router.get("/health")
        async def health_check():
            """فحص الصحة."""
            llm_healthy = False

            if self.llm_provider:
                llm_healthy = await self.llm_provider.health_check()

            return {
                "status": "healthy" if llm_healthy else "degraded",
                "llm_provider": llm_healthy,
            }

        @self.router.websocket("/ws/{conversation_id}")
        async def websocket_chat(websocket: WebSocket, conversation_id: str):
            """WebSocket للمحادثة المباشرة."""
            await websocket.accept()

            # Register connection
            if conversation_id not in self._websockets:
                self._websockets[conversation_id] = []
            self._websockets[conversation_id].append(websocket)

            try:
                while True:
                    # Receive message
                    data = await websocket.receive_json()
                    message = data.get("message", "")

                    if not message:
                        continue

                    # Get conversation
                    conv = self.manager.get_conversation(conversation_id)
                    if not conv:
                        await websocket.send_json({
                            "error": "Conversation not found"
                        })
                        continue

                    # Stream response
                    config = GenerationConfig(
                        temperature=data.get("temperature", 0.7),
                        max_tokens=data.get("max_tokens", 2048),
                    )

                    full_response = []

                    async for chunk in self.manager.chat_stream(conv, message, config):
                        full_response.append(chunk)
                        await websocket.send_json({
                            "type": "chunk",
                            "content": chunk,
                        })

                    # Send complete message
                    await websocket.send_json({
                        "type": "complete",
                        "content": "".join(full_response),
                        "conversation_id": conversation_id,
                    })

            except WebSocketDisconnect:
                # Remove connection
                if conversation_id in self._websockets:
                    self._websockets[conversation_id].remove(websocket)

    async def _stream_response(
        self,
        conversation: Conversation,
        message: str,
        config: GenerationConfig,
    ):
        """Stream response as Server-Sent Events."""
        import json

        async for chunk in self.manager.chat_stream(conversation, message, config):
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        yield f"data: {json.dumps({'done': True, 'conversation_id': conversation.conversation_id})}\n\n"

    async def _broadcast(
        self,
        conversation_id: str,
        message: Message,
    ) -> None:
        """Broadcast message to WebSocket clients."""
        if conversation_id not in self._websockets:
            return

        data = {
            "type": "message",
            "message": message.to_dict(),
        }

        disconnected = []

        for ws in self._websockets[conversation_id]:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)

        # Remove disconnected clients
        for ws in disconnected:
            self._websockets[conversation_id].remove(ws)


def create_chat_router(
    llm_provider: LLMProvider,
    storage_dir: Optional[str] = None,
    default_model: str = "llama3.2",
    default_system_prompt: Optional[str] = None,
) -> APIRouter:
    """إنشاء router للمحادثة."""
    from pathlib import Path

    manager = ConversationManager(
        storage_dir=Path(storage_dir) if storage_dir else None,
        llm_provider=llm_provider,
        default_model=default_model,
        default_system_prompt=default_system_prompt,
    )

    api = ChatAPI(manager, llm_provider)

    return api.router
