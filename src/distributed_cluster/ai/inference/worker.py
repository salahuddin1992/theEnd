"""
Inference Worker - عامل الاستنتاج
==================================

Worker node that serves LLM inference requests.
Can be deployed on machines with GPUs.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from distributed_cluster.ai.llm.provider import (
    LLMProvider,
    LLMResponse,
    GenerationConfig,
    OllamaProvider,
    VLLMProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """تكوين العامل."""
    worker_id: str = ""
    name: str = "inference-worker"
    host: str = "0.0.0.0"
    port: int = 8080

    # Master registration
    master_url: Optional[str] = None
    heartbeat_interval: float = 30.0

    # LLM backend
    llm_provider: str = "ollama"  # ollama, vllm
    llm_url: str = "http://localhost:11434"

    # Resources
    max_concurrent: int = 10
    gpu_ids: List[int] = field(default_factory=list)

    # Models to serve
    models: List[str] = field(default_factory=list)


class GenerateRequest(BaseModel):
    """طلب التوليد."""
    prompt: str
    model: str
    system_prompt: Optional[str] = None
    stream: bool = False

    # Generation config
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    stop_sequences: List[str] = []


class ChatRequest(BaseModel):
    """طلب المحادثة."""
    messages: List[Dict[str, str]]
    model: str
    stream: bool = False

    temperature: float = 0.7
    max_tokens: int = 2048


class InferenceWorker:
    """
    عامل الاستنتاج.

    Serves LLM inference requests and registers with master.
    """

    def __init__(self, config: WorkerConfig):
        self.config = config
        self.worker_id = config.worker_id or f"worker-{os.getpid()}"

        # LLM provider
        self._provider: Optional[LLMProvider] = None

        # Statistics
        self._stats = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "active_requests": 0,
            "tokens_generated": 0,
            "started_at": None,
        }

        # State
        self._running = False
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

        # FastAPI app
        self.app = FastAPI(
            title="Inference Worker",
            description="Distributed LLM Inference Worker",
        )
        self._setup_routes()

    def _setup_routes(self) -> None:
        """إعداد المسارات."""

        @self.app.on_event("startup")
        async def startup():
            await self.start()

        @self.app.on_event("shutdown")
        async def shutdown():
            await self.stop()

        @self.app.get("/health")
        async def health():
            """فحص الصحة."""
            provider_healthy = False
            if self._provider:
                provider_healthy = await self._provider.health_check()

            return {
                "status": "healthy" if provider_healthy else "degraded",
                "worker_id": self.worker_id,
                "provider": self.config.llm_provider,
                "provider_healthy": provider_healthy,
            }

        @self.app.get("/info")
        async def info():
            """معلومات العامل."""
            models = []
            if self._provider:
                try:
                    model_list = await self._provider.list_models()
                    models = [m.name for m in model_list]
                except Exception:
                    pass

            return {
                "worker_id": self.worker_id,
                "name": self.config.name,
                "provider": self.config.llm_provider,
                "models": models,
                "max_concurrent": self.config.max_concurrent,
                "gpu_ids": self.config.gpu_ids,
                "stats": self._stats,
            }

        @self.app.get("/models")
        async def list_models():
            """قائمة النماذج."""
            if not self._provider:
                raise HTTPException(status_code=503, detail="Provider not ready")

            models = await self._provider.list_models()
            return {
                "models": [
                    {
                        "name": m.name,
                        "size_bytes": m.size_bytes,
                        "parameter_size": m.parameter_size,
                    }
                    for m in models
                ]
            }

        @self.app.post("/generate")
        async def generate(request: GenerateRequest):
            """توليد نص."""
            if not self._provider:
                raise HTTPException(status_code=503, detail="Provider not ready")

            async with self._semaphore:
                self._stats["requests_total"] += 1
                self._stats["active_requests"] += 1

                try:
                    config = GenerationConfig(
                        temperature=request.temperature,
                        top_p=request.top_p,
                        top_k=request.top_k,
                        max_tokens=request.max_tokens,
                        stop_sequences=request.stop_sequences,
                    )

                    if request.stream:
                        return StreamingResponse(
                            self._stream_generate(
                                request.prompt,
                                request.model,
                                config,
                                request.system_prompt,
                            ),
                            media_type="text/event-stream",
                        )

                    response = await self._provider.generate(
                        prompt=request.prompt,
                        model=request.model,
                        config=config,
                        system_prompt=request.system_prompt,
                    )

                    self._stats["requests_success"] += 1
                    self._stats["tokens_generated"] += response.total_tokens

                    return {
                        "text": response.text,
                        "model": response.model,
                        "tokens": response.total_tokens,
                        "generation_time_ms": response.generation_time_ms,
                        "tokens_per_second": response.tokens_per_second,
                    }

                except Exception as e:
                    self._stats["requests_failed"] += 1
                    logger.error(f"Generate failed: {e}")
                    raise HTTPException(status_code=500, detail=str(e))

                finally:
                    self._stats["active_requests"] -= 1

        @self.app.post("/chat")
        async def chat(request: ChatRequest):
            """محادثة."""
            if not self._provider:
                raise HTTPException(status_code=503, detail="Provider not ready")

            async with self._semaphore:
                self._stats["requests_total"] += 1
                self._stats["active_requests"] += 1

                try:
                    config = GenerationConfig(
                        temperature=request.temperature,
                        max_tokens=request.max_tokens,
                    )

                    if request.stream:
                        return StreamingResponse(
                            self._stream_chat(
                                request.messages,
                                request.model,
                                config,
                            ),
                            media_type="text/event-stream",
                        )

                    response = await self._provider.chat(
                        messages=request.messages,
                        model=request.model,
                        config=config,
                    )

                    self._stats["requests_success"] += 1
                    self._stats["tokens_generated"] += response.total_tokens

                    return {
                        "text": response.text,
                        "model": response.model,
                        "tokens": response.total_tokens,
                        "generation_time_ms": response.generation_time_ms,
                    }

                except Exception as e:
                    self._stats["requests_failed"] += 1
                    logger.error(f"Chat failed: {e}")
                    raise HTTPException(status_code=500, detail=str(e))

                finally:
                    self._stats["active_requests"] -= 1

        @self.app.get("/stats")
        async def stats():
            """إحصائيات."""
            return self._stats

    async def _stream_generate(
        self,
        prompt: str,
        model: str,
        config: GenerationConfig,
        system_prompt: Optional[str],
    ):
        """Stream generation."""
        import json

        try:
            async for chunk in self._provider.generate_stream(
                prompt=prompt,
                model=model,
                config=config,
                system_prompt=system_prompt,
            ):
                yield f"data: {json.dumps({'text': chunk})}\n\n"

            self._stats["requests_success"] += 1
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            self._stats["requests_failed"] += 1
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    async def _stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str,
        config: GenerationConfig,
    ):
        """Stream chat."""
        import json

        if hasattr(self._provider, 'chat_stream'):
            try:
                async for chunk in self._provider.chat_stream(
                    messages=messages,
                    model=model,
                    config=config,
                ):
                    yield f"data: {json.dumps({'text': chunk})}\n\n"

                self._stats["requests_success"] += 1
                yield f"data: {json.dumps({'done': True})}\n\n"

            except Exception as e:
                self._stats["requests_failed"] += 1
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        else:
            # Fallback to non-streaming
            response = await self._provider.chat(messages, model, config)
            yield f"data: {json.dumps({'text': response.text, 'done': True})}\n\n"

    async def start(self) -> None:
        """بدء العامل."""
        if self._running:
            return

        logger.info(f"Starting inference worker: {self.worker_id}")

        # Initialize provider
        if self.config.llm_provider == "ollama":
            self._provider = OllamaProvider(base_url=self.config.llm_url)
        elif self.config.llm_provider == "vllm":
            self._provider = VLLMProvider(base_url=self.config.llm_url)
        else:
            raise ValueError(f"Unknown provider: {self.config.llm_provider}")

        # Check provider health
        healthy = await self._provider.health_check()
        if not healthy:
            logger.warning(f"LLM provider at {self.config.llm_url} is not healthy")

        self._stats["started_at"] = datetime.utcnow().isoformat()
        self._running = True

        # Register with master if configured
        if self.config.master_url:
            asyncio.create_task(self._registration_loop())

        logger.info(f"Inference worker started: {self.worker_id}")

    async def stop(self) -> None:
        """إيقاف العامل."""
        self._running = False

        if self._provider:
            await self._provider.close()

        # Deregister from master
        if self.config.master_url:
            await self._deregister()

        logger.info(f"Inference worker stopped: {self.worker_id}")

    async def _registration_loop(self) -> None:
        """حلقة التسجيل."""
        while self._running:
            try:
                await self._register()
                await asyncio.sleep(self.config.heartbeat_interval)
            except Exception as e:
                logger.error(f"Registration failed: {e}")
                await asyncio.sleep(5)

    async def _register(self) -> None:
        """التسجيل مع Master."""
        if not self.config.master_url:
            return

        models = []
        if self._provider:
            try:
                model_list = await self._provider.list_models()
                models = [m.name for m in model_list]
            except Exception:
                pass

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.config.master_url}/ai/workers/register",
                json={
                    "worker_id": self.worker_id,
                    "name": self.config.name,
                    "url": f"http://{self.config.host}:{self.config.port}",
                    "provider": self.config.llm_provider,
                    "models": models,
                    "max_concurrent": self.config.max_concurrent,
                    "gpu_ids": self.config.gpu_ids,
                    "stats": self._stats,
                },
                timeout=10.0,
            )

    async def _deregister(self) -> None:
        """إلغاء التسجيل."""
        if not self.config.master_url:
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.config.master_url}/ai/workers/deregister",
                    json={"worker_id": self.worker_id},
                    timeout=5.0,
                )
        except Exception as e:
            logger.warning(f"Deregistration failed: {e}")

    def run(self) -> None:
        """تشغيل العامل."""
        uvicorn.run(
            self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info",
        )


def create_worker_from_env() -> InferenceWorker:
    """إنشاء عامل من متغيرات البيئة."""
    config = WorkerConfig(
        worker_id=os.getenv("WORKER_ID", ""),
        name=os.getenv("WORKER_NAME", "inference-worker"),
        host=os.getenv("WORKER_HOST", "0.0.0.0"),
        port=int(os.getenv("WORKER_PORT", "8080")),
        master_url=os.getenv("MASTER_URL"),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        llm_url=os.getenv("LLM_URL", "http://localhost:11434"),
        max_concurrent=int(os.getenv("MAX_CONCURRENT", "10")),
    )

    gpu_ids = os.getenv("GPU_IDS", "")
    if gpu_ids:
        config.gpu_ids = [int(x) for x in gpu_ids.split(",")]

    return InferenceWorker(config)


# CLI entry point
def main():
    """نقطة الدخول."""
    import argparse

    parser = argparse.ArgumentParser(description="Inference Worker")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--master", help="Master URL for registration")
    parser.add_argument("--provider", default="ollama", help="LLM provider")
    parser.add_argument("--llm-url", default="http://localhost:11434", help="LLM URL")
    parser.add_argument("--max-concurrent", type=int, default=10, help="Max concurrent")

    args = parser.parse_args()

    config = WorkerConfig(
        host=args.host,
        port=args.port,
        master_url=args.master,
        llm_provider=args.provider,
        llm_url=args.llm_url,
        max_concurrent=args.max_concurrent,
    )

    worker = InferenceWorker(config)
    worker.run()


if __name__ == "__main__":
    main()
