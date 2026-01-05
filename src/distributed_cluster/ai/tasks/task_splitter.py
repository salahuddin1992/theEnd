"""
Task Splitter - تقسيم المهام الكبيرة
=====================================

Automatically splits large AI tasks across multiple workers.

Features:
- Intelligent text chunking
- Load balancing across workers
- Result aggregation
- Parallel execution
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from distributed_cluster.ai.tasks.builtin_tasks import AITask, TaskResult

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    """استراتيجيات تقسيم النص."""

    FIXED_SIZE = "fixed_size"  # حجم ثابت
    SENTENCE = "sentence"  # جمل
    PARAGRAPH = "paragraph"  # فقرات
    SEMANTIC = "semantic"  # دلالي
    TOKEN_BASED = "token_based"  # بناءً على التوكنز
    CUSTOM = "custom"  # مخصص


class AggregationStrategy(str, Enum):
    """استراتيجيات تجميع النتائج."""

    CONCATENATE = "concatenate"  # ربط
    MERGE_JSON = "merge_json"  # دمج JSON
    SUMMARIZE = "summarize"  # تلخيص
    VOTE = "vote"  # تصويت
    BEST_SCORE = "best_score"  # أفضل نتيجة
    CUSTOM = "custom"  # مخصص


@dataclass
class TaskChunk:
    """قطعة من المهمة."""

    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str = ""
    sequence: int = 0
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: int = 0

    # Execution state
    worker_id: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """تحويل لقاموس."""
        return {
            "chunk_id": self.chunk_id,
            "parent_task_id": self.parent_task_id,
            "sequence": self.sequence,
            "content": self.content,
            "metadata": self.metadata,
            "token_count": self.token_count,
            "worker_id": self.worker_id,
            "status": self.status,
        }


@dataclass
class SplitTask:
    """مهمة مقسمة."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_task: Optional[AITask] = None
    prompt_template: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    chunks: List[TaskChunk] = field(default_factory=list)
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.PARAGRAPH
    aggregation_strategy: AggregationStrategy = AggregationStrategy.CONCATENATE
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Progress
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0

    # Results
    final_result: Optional[Any] = None
    aggregation_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        """نسبة الإنجاز."""
        if self.total_chunks == 0:
            return 0.0
        return (self.completed_chunks / self.total_chunks) * 100

    @property
    def is_complete(self) -> bool:
        """هل اكتملت؟"""
        return self.completed_chunks + self.failed_chunks >= self.total_chunks


class TextChunker:
    """مقسم النصوص."""

    # Approximate tokens per character (for estimation)
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        max_chunk_tokens: int = 2000,
        overlap_tokens: int = 100,
    ):
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens

    def estimate_tokens(self, text: str) -> int:
        """تقدير عدد التوكنز."""
        return len(text) // self.CHARS_PER_TOKEN

    def chunk_fixed_size(self, text: str) -> List[str]:
        """تقسيم بحجم ثابت."""
        max_chars = self.max_chunk_tokens * self.CHARS_PER_TOKEN
        overlap_chars = self.overlap_tokens * self.CHARS_PER_TOKEN

        chunks = []
        start = 0

        while start < len(text):
            end = min(start + max_chars, len(text))

            # Try to break at word boundary
            if end < len(text):
                space_idx = text.rfind(" ", start, end)
                if space_idx > start:
                    end = space_idx

            chunks.append(text[start:end].strip())
            start = end - overlap_chars if overlap_chars > 0 else end

        return chunks

    def chunk_by_sentences(self, text: str) -> List[str]:
        """تقسيم بالجمل."""
        # Split by sentence endings
        sentences = re.split(r"(?<=[.!?])\s+", text)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in sentences:
            sentence_tokens = self.estimate_tokens(sentence)

            if current_tokens + sentence_tokens > self.max_chunk_tokens:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_tokens = sentence_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def chunk_by_paragraphs(self, text: str) -> List[str]:
        """تقسيم بالفقرات."""
        paragraphs = re.split(r"\n\s*\n", text)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self.estimate_tokens(para)

            # If single paragraph is too long, split it further
            if para_tokens > self.max_chunk_tokens:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0

                # Split long paragraph by sentences
                sub_chunks = self.chunk_by_sentences(para)
                chunks.extend(sub_chunks)
            elif current_tokens + para_tokens > self.max_chunk_tokens:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def chunk(
        self,
        text: str,
        strategy: ChunkingStrategy = ChunkingStrategy.PARAGRAPH,
    ) -> List[str]:
        """تقسيم النص حسب الاستراتيجية."""
        if strategy == ChunkingStrategy.FIXED_SIZE:
            return self.chunk_fixed_size(text)
        elif strategy == ChunkingStrategy.SENTENCE:
            return self.chunk_by_sentences(text)
        elif strategy == ChunkingStrategy.PARAGRAPH:
            return self.chunk_by_paragraphs(text)
        elif strategy == ChunkingStrategy.TOKEN_BASED:
            return self.chunk_fixed_size(text)
        else:
            # Default to paragraph
            return self.chunk_by_paragraphs(text)


class ResultAggregator:
    """مجمع النتائج."""

    def concatenate(self, results: List[Any], separator: str = "\n\n") -> str:
        """ربط النتائج."""
        return separator.join(str(r) for r in results if r)

    def merge_json(self, results: List[Any]) -> Dict[str, Any]:
        """دمج نتائج JSON."""
        merged: Dict[str, Any] = {}

        for result in results:
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    continue

            if isinstance(result, dict):
                for key, value in result.items():
                    if key in merged:
                        if isinstance(merged[key], list):
                            if isinstance(value, list):
                                merged[key].extend(value)
                            else:
                                merged[key].append(value)
                        else:
                            merged[key] = [merged[key], value]
                    else:
                        merged[key] = value

        return merged

    def vote(self, results: List[Any]) -> Any:
        """تصويت - الأكثر تكراراً."""
        if not results:
            return None

        from collections import Counter

        counter = Counter(str(r) for r in results)
        return counter.most_common(1)[0][0]

    def aggregate(
        self,
        results: List[Any],
        strategy: AggregationStrategy = AggregationStrategy.CONCATENATE,
        **kwargs,
    ) -> Any:
        """تجميع النتائج حسب الاستراتيجية."""
        if strategy == AggregationStrategy.CONCATENATE:
            return self.concatenate(results, kwargs.get("separator", "\n\n"))
        elif strategy == AggregationStrategy.MERGE_JSON:
            return self.merge_json(results)
        elif strategy == AggregationStrategy.VOTE:
            return self.vote(results)
        else:
            return self.concatenate(results)


class TaskSplitter:
    """
    مقسم المهام - يقسم المهام الكبيرة على عدة Workers.

    Features:
    - Automatic text chunking
    - Smart distribution across workers
    - Progress tracking
    - Result aggregation
    """

    def __init__(
        self,
        max_chunk_tokens: int = 2000,
        overlap_tokens: int = 100,
        default_chunking: ChunkingStrategy = ChunkingStrategy.PARAGRAPH,
        default_aggregation: AggregationStrategy = AggregationStrategy.CONCATENATE,
    ):
        self.chunker = TextChunker(max_chunk_tokens, overlap_tokens)
        self.aggregator = ResultAggregator()
        self.default_chunking = default_chunking
        self.default_aggregation = default_aggregation

    def should_split(
        self,
        text: str,
        max_tokens: int = 4000,
    ) -> bool:
        """هل يجب تقسيم النص؟"""
        estimated_tokens = self.chunker.estimate_tokens(text)
        return estimated_tokens > max_tokens

    def split_task(
        self,
        task: AITask,
        parameters: Dict[str, Any],
        text_param: str = "text",
        chunking_strategy: Optional[ChunkingStrategy] = None,
        aggregation_strategy: Optional[AggregationStrategy] = None,
    ) -> SplitTask:
        """تقسيم مهمة AI."""
        chunking = chunking_strategy or self.default_chunking
        aggregation = aggregation_strategy or self.default_aggregation

        # Get the text to split
        text = parameters.get(text_param, "")

        if not text:
            raise ValueError(f"Parameter '{text_param}' is required for splitting")

        # Create chunks
        text_chunks = self.chunker.chunk(text, chunking)

        split_task = SplitTask(
            original_task=task,
            prompt_template=task.prompt_template,
            parameters=parameters.copy(),
            chunking_strategy=chunking,
            aggregation_strategy=aggregation,
            total_chunks=len(text_chunks),
        )

        # Create chunk objects
        for i, chunk_text in enumerate(text_chunks):
            chunk = TaskChunk(
                parent_task_id=split_task.task_id,
                sequence=i,
                content=chunk_text,
                token_count=self.chunker.estimate_tokens(chunk_text),
                metadata={
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                    "text_param": text_param,
                },
            )
            split_task.chunks.append(chunk)

        return split_task

    def split_prompt(
        self,
        prompt: str,
        text: str,
        text_placeholder: str = "{text}",
        chunking_strategy: Optional[ChunkingStrategy] = None,
    ) -> List[str]:
        """تقسيم prompt مع النص."""
        chunking = chunking_strategy or self.default_chunking
        text_chunks = self.chunker.chunk(text, chunking)

        prompts = []
        for i, chunk in enumerate(text_chunks):
            chunk_prompt = prompt.replace(text_placeholder, chunk)

            # Add chunk metadata to prompt
            chunk_prompt = f"[Chunk {i + 1}/{len(text_chunks)}]\n\n{chunk_prompt}"
            prompts.append(chunk_prompt)

        return prompts

    def aggregate_results(
        self,
        split_task: SplitTask,
    ) -> Any:
        """تجميع نتائج المهمة المقسمة."""
        # Sort chunks by sequence
        sorted_chunks = sorted(split_task.chunks, key=lambda c: c.sequence)

        # Get results
        results = [c.result for c in sorted_chunks if c.result is not None]

        if not results:
            return None

        # Aggregate
        aggregated = self.aggregator.aggregate(
            results,
            split_task.aggregation_strategy,
        )

        split_task.final_result = aggregated
        split_task.aggregation_metadata = {
            "total_chunks": len(sorted_chunks),
            "successful_chunks": len(results),
            "strategy": split_task.aggregation_strategy.value,
        }

        return aggregated


@dataclass
class WorkerInfo:
    """معلومات Worker."""

    worker_id: str
    capacity: int = 1  # عدد المهام المتزامنة
    current_load: int = 0
    avg_latency_ms: float = 0
    success_rate: float = 1.0
    specializations: List[str] = field(default_factory=list)

    @property
    def available_capacity(self) -> int:
        return max(0, self.capacity - self.current_load)


class DistributedPromptExecutor:
    """
    منفذ Prompts الموزعة.

    Distributes AI prompts across multiple workers for parallel execution.
    """

    def __init__(
        self,
        master_url: Optional[str] = None,
        max_concurrent_per_worker: int = 3,
        timeout_seconds: float = 300,
        retry_count: int = 2,
    ):
        self.master_url = master_url
        self.max_concurrent = max_concurrent_per_worker
        self.timeout = timeout_seconds
        self.retry_count = retry_count

        self.splitter = TaskSplitter()
        self._workers: Dict[str, WorkerInfo] = {}
        self._pending_tasks: Dict[str, SplitTask] = {}

        # Stats
        self._total_prompts = 0
        self._completed_prompts = 0
        self._failed_prompts = 0

    def register_worker(self, worker: WorkerInfo) -> None:
        """تسجيل Worker."""
        self._workers[worker.worker_id] = worker
        logger.info(f"Registered worker: {worker.worker_id}")

    def unregister_worker(self, worker_id: str) -> None:
        """إلغاء تسجيل Worker."""
        if worker_id in self._workers:
            del self._workers[worker_id]

    def get_available_workers(self) -> List[WorkerInfo]:
        """الحصول على Workers المتاحة."""
        return [w for w in self._workers.values() if w.available_capacity > 0]

    def _select_worker(self, chunk: TaskChunk) -> Optional[WorkerInfo]:
        """اختيار Worker للقطعة."""
        available = self.get_available_workers()

        if not available:
            return None

        # Sort by load (least loaded first) then by latency
        available.sort(key=lambda w: (w.current_load, w.avg_latency_ms))

        return available[0]

    async def execute_distributed(
        self,
        task: AITask,
        parameters: Dict[str, Any],
        text_param: str = "text",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> TaskResult:
        """
        تنفيذ مهمة موزعة.

        Args:
            task: المهمة
            parameters: المعاملات
            text_param: اسم معامل النص
            on_progress: callback للتقدم

        Returns:
            نتيجة المهمة
        """
        start_time = time.time()
        task_id = str(uuid.uuid4())

        text = parameters.get(text_param, "")

        # Check if splitting is needed
        if not self.splitter.should_split(text, task.max_input_tokens):
            # Execute as single task
            result = await self._execute_single(task, parameters)
            return TaskResult(
                task_id=task_id,
                task_name=task.name,
                success=result.get("success", False),
                output=result.get("output"),
                error=result.get("error"),
                execution_time_ms=(time.time() - start_time) * 1000,
                tokens_used=result.get("tokens", 0),
            )

        # Split the task
        split_task = self.splitter.split_task(
            task,
            parameters,
            text_param,
        )
        self._pending_tasks[split_task.task_id] = split_task

        if on_progress:
            on_progress(0, f"Split into {split_task.total_chunks} chunks")

        # Execute chunks in parallel
        results = await self._execute_chunks_parallel(
            split_task,
            task,
            parameters,
            text_param,
            on_progress,
        )

        # Aggregate results
        final_result = self.splitter.aggregate_results(split_task)

        execution_time = (time.time() - start_time) * 1000

        return TaskResult(
            task_id=task_id,
            task_name=task.name,
            success=split_task.failed_chunks == 0,
            output=final_result,
            error=None if split_task.failed_chunks == 0 else f"{split_task.failed_chunks} chunks failed",
            execution_time_ms=execution_time,
            tokens_used=sum(c.token_count for c in split_task.chunks),
            metadata={
                "distributed": True,
                "total_chunks": split_task.total_chunks,
                "completed_chunks": split_task.completed_chunks,
                "failed_chunks": split_task.failed_chunks,
                "workers_used": list({c.worker_id for c in split_task.chunks if c.worker_id}),
            },
        )

    async def _execute_chunks_parallel(
        self,
        split_task: SplitTask,
        task: AITask,
        parameters: Dict[str, Any],
        text_param: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> List[Any]:
        """تنفيذ القطع بالتوازي."""
        semaphore = asyncio.Semaphore(len(self._workers) * self.max_concurrent)

        async def execute_chunk(chunk: TaskChunk) -> Any:
            async with semaphore:
                chunk.status = "running"
                chunk_start = time.time()

                try:
                    # Select worker
                    worker = self._select_worker(chunk)
                    if worker:
                        chunk.worker_id = worker.worker_id
                        worker.current_load += 1

                    # Build chunk parameters
                    chunk_params = parameters.copy()
                    chunk_params[text_param] = chunk.content

                    # Execute
                    result = await self._execute_on_worker(
                        task,
                        chunk_params,
                        worker.worker_id if worker else None,
                    )

                    chunk.result = result.get("output")
                    chunk.status = "completed"
                    split_task.completed_chunks += 1

                    if worker:
                        worker.current_load -= 1

                    if on_progress:
                        progress = split_task.progress
                        on_progress(progress, f"Completed chunk {chunk.sequence + 1}/{split_task.total_chunks}")

                    return chunk.result

                except Exception as e:
                    chunk.status = "failed"
                    chunk.error = str(e)
                    split_task.failed_chunks += 1

                    logger.error(f"Chunk {chunk.chunk_id} failed: {e}")
                    return None

                finally:
                    chunk.execution_time_ms = (time.time() - chunk_start) * 1000

        # Execute all chunks
        tasks = [execute_chunk(chunk) for chunk in split_task.chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return results

    async def _execute_single(
        self,
        task: AITask,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """تنفيذ مهمة واحدة."""
        worker = self._select_worker(TaskChunk())

        return await self._execute_on_worker(
            task,
            parameters,
            worker.worker_id if worker else None,
        )

    async def _execute_on_worker(
        self,
        task: AITask,
        parameters: Dict[str, Any],
        worker_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """تنفيذ على Worker محدد."""
        if not self.master_url:
            # Local execution simulation
            return await self._execute_local(task, parameters)

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Build prompt
            prompt = task.build_prompt(**parameters)

            payload = {
                "task_id": task.task_id,
                "prompt": prompt,
                "parameters": parameters,
                "worker_id": worker_id,
            }

            for attempt in range(self.retry_count + 1):
                try:
                    response = await client.post(
                        f"{self.master_url}/ai/execute",
                        json=payload,
                    )
                    response.raise_for_status()
                    return response.json()

                except httpx.HTTPError as e:
                    if attempt == self.retry_count:
                        raise
                    await asyncio.sleep(2**attempt)

        return {"success": False, "error": "Max retries exceeded"}

    async def _execute_local(
        self,
        task: AITask,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """تنفيذ محلي (للاختبار)."""
        # This would normally call the LLM provider
        # For now, return a placeholder
        prompt = task.build_prompt(**parameters)

        return {
            "success": True,
            "output": f"[Simulated output for: {task.name}]\n\nPrompt length: {len(prompt)} chars",
            "tokens": len(prompt) // 4,
        }

    async def execute_batch(
        self,
        prompts: List[Dict[str, Any]],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> List[TaskResult]:
        """
        تنفيذ دفعة من الـ prompts.

        Args:
            prompts: قائمة الـ prompts مع parameters
            on_progress: callback للتقدم (completed, total)

        Returns:
            قائمة النتائج
        """
        results = []
        total = len(prompts)

        for i, prompt_data in enumerate(prompts):
            task = prompt_data.get("task")
            parameters = prompt_data.get("parameters", {})

            if isinstance(task, str):
                # Get task from registry
                from distributed_cluster.ai.tasks.builtin_tasks import get_builtin_tasks

                registry = get_builtin_tasks()
                task = registry.get(task)

            if task:
                result = await self.execute_distributed(task, parameters)
                results.append(result)
            else:
                results.append(
                    TaskResult(
                        task_id=str(uuid.uuid4()),
                        task_name="unknown",
                        success=False,
                        error="Task not found",
                    )
                )

            if on_progress:
                on_progress(i + 1, total)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات التنفيذ."""
        return {
            "total_prompts": self._total_prompts,
            "completed_prompts": self._completed_prompts,
            "failed_prompts": self._failed_prompts,
            "success_rate": (
                self._completed_prompts / self._total_prompts if self._total_prompts > 0 else 0
            ),
            "active_workers": len(self._workers),
            "available_capacity": sum(w.available_capacity for w in self._workers.values()),
            "pending_tasks": len(self._pending_tasks),
        }
