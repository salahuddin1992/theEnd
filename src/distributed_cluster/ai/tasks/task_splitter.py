"""
Task Splitter - تقسيم المهام
=============================

Split large tasks for distributed execution.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ChunkingStrategy(str, Enum):
    """استراتيجيات التقسيم."""
    SENTENCE = "sentence"       # Split by sentences
    PARAGRAPH = "paragraph"     # Split by paragraphs
    TOKEN = "token"             # Split by token count
    CHARACTER = "character"     # Split by character count
    LINE = "line"               # Split by lines
    SEMANTIC = "semantic"       # Split by semantic units (advanced)
    CUSTOM = "custom"           # Custom splitter function


@dataclass
class TaskChunk:
    """جزء من المهمة."""
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    index: int = 0
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Result
    result: Optional[str] = None
    error: Optional[str] = None
    processed: bool = False

    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "index": self.index,
            "content": self.content[:100] + "..." if len(self.content) > 100 else self.content,
            "metadata": self.metadata,
            "processed": self.processed,
            "has_result": self.result is not None,
            "error": self.error,
        }


class TaskSplitter:
    """
    تقسيم المهام الكبيرة.

    Features:
    - Multiple chunking strategies
    - Overlap support for context preservation
    - Token-aware splitting
    - Semantic chunking (advanced)
    """

    def __init__(
        self,
        strategy: ChunkingStrategy = ChunkingStrategy.PARAGRAPH,
        max_chunk_size: int = 4000,  # characters
        overlap: int = 200,          # overlap between chunks
        min_chunk_size: int = 100,   # minimum chunk size
    ):
        self.strategy = strategy
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.min_chunk_size = min_chunk_size

    def split(self, text: str) -> List[TaskChunk]:
        """
        تقسيم النص إلى أجزاء.

        Args:
            text: النص المراد تقسيمه

        Returns:
            قائمة الأجزاء
        """
        if not text or len(text) <= self.max_chunk_size:
            return [TaskChunk(index=0, content=text)]

        if self.strategy == ChunkingStrategy.SENTENCE:
            return self._split_by_sentence(text)
        elif self.strategy == ChunkingStrategy.PARAGRAPH:
            return self._split_by_paragraph(text)
        elif self.strategy == ChunkingStrategy.LINE:
            return self._split_by_line(text)
        elif self.strategy == ChunkingStrategy.CHARACTER:
            return self._split_by_character(text)
        elif self.strategy == ChunkingStrategy.TOKEN:
            return self._split_by_token(text)
        else:
            return self._split_by_character(text)

    def _split_by_sentence(self, text: str) -> List[TaskChunk]:
        """تقسيم حسب الجمل."""
        # Split on sentence boundaries
        sentence_endings = r'(?<=[.!?])\s+'
        sentences = re.split(sentence_endings, text)

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_len = len(sentence)

            if current_length + sentence_len > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunk_text = " ".join(current_chunk)
                chunks.append(TaskChunk(
                    index=len(chunks),
                    content=chunk_text,
                    metadata={"strategy": "sentence", "sentences": len(current_chunk)},
                ))

                # Start new chunk with overlap
                if self.overlap > 0 and current_chunk:
                    # Keep last sentence(s) for overlap
                    overlap_text = current_chunk[-1]
                    current_chunk = [overlap_text]
                    current_length = len(overlap_text)
                else:
                    current_chunk = []
                    current_length = 0

            current_chunk.append(sentence)
            current_length += sentence_len

        # Add remaining
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(TaskChunk(
                index=len(chunks),
                content=chunk_text,
                metadata={"strategy": "sentence", "sentences": len(current_chunk)},
            ))

        return chunks

    def _split_by_paragraph(self, text: str) -> List[TaskChunk]:
        """تقسيم حسب الفقرات."""
        paragraphs = re.split(r'\n\s*\n', text)

        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_len = len(para)

            if current_length + para_len > self.max_chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(TaskChunk(
                    index=len(chunks),
                    content=chunk_text,
                    metadata={"strategy": "paragraph", "paragraphs": len(current_chunk)},
                ))

                # Overlap
                if self.overlap > 0 and current_chunk:
                    current_chunk = [current_chunk[-1]]
                    current_length = len(current_chunk[-1])
                else:
                    current_chunk = []
                    current_length = 0

            current_chunk.append(para)
            current_length += para_len

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(TaskChunk(
                index=len(chunks),
                content=chunk_text,
                metadata={"strategy": "paragraph", "paragraphs": len(current_chunk)},
            ))

        return chunks

    def _split_by_line(self, text: str) -> List[TaskChunk]:
        """تقسيم حسب الأسطر."""
        lines = text.split('\n')

        chunks = []
        current_chunk = []
        current_length = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline

            if current_length + line_len > self.max_chunk_size and current_chunk:
                chunk_text = "\n".join(current_chunk)
                chunks.append(TaskChunk(
                    index=len(chunks),
                    content=chunk_text,
                    metadata={"strategy": "line", "lines": len(current_chunk)},
                ))

                current_chunk = []
                current_length = 0

            current_chunk.append(line)
            current_length += line_len

        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunks.append(TaskChunk(
                index=len(chunks),
                content=chunk_text,
                metadata={"strategy": "line", "lines": len(current_chunk)},
            ))

        return chunks

    def _split_by_character(self, text: str) -> List[TaskChunk]:
        """تقسيم حسب الأحرف."""
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.max_chunk_size, len(text))

            # Try to break at word boundary
            if end < len(text):
                last_space = text.rfind(' ', start, end)
                if last_space > start:
                    end = last_space

            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append(TaskChunk(
                    index=len(chunks),
                    content=chunk_text,
                    metadata={"strategy": "character", "start": start, "end": end},
                ))

            # Move start with overlap
            start = end - self.overlap if self.overlap > 0 else end

        return chunks

    def _split_by_token(self, text: str) -> List[TaskChunk]:
        """تقسيم حسب الـ tokens (تقريبي)."""
        # Approximate: 1 token ≈ 4 characters
        token_to_char = 4
        effective_max = self.max_chunk_size * token_to_char

        # Use character splitting with adjusted size
        original_max = self.max_chunk_size
        self.max_chunk_size = effective_max

        chunks = self._split_by_character(text)

        self.max_chunk_size = original_max

        # Update metadata
        for chunk in chunks:
            chunk.metadata["strategy"] = "token"
            chunk.metadata["approx_tokens"] = len(chunk.content) // token_to_char

        return chunks


class DistributedPromptExecutor:
    """
    منفذ موزع للـ prompts.

    Executes prompts in parallel across chunks.
    """

    def __init__(
        self,
        splitter: Optional[TaskSplitter] = None,
        max_concurrent: int = 5,
    ):
        self.splitter = splitter or TaskSplitter()
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(
        self,
        text: str,
        prompt_template: str,
        executor_fn,
        aggregate_fn=None,
    ) -> Dict[str, Any]:
        """
        تنفيذ موزع.

        Args:
            text: النص المراد معالجته
            prompt_template: قالب الـ prompt مع {chunk}
            executor_fn: دالة التنفيذ async (prompt) -> result
            aggregate_fn: دالة تجميع النتائج (results) -> final

        Returns:
            النتيجة النهائية
        """
        # Split text
        chunks = self.splitter.split(text)

        logger.info(f"Split text into {len(chunks)} chunks")

        # Execute in parallel
        tasks = []
        for chunk in chunks:
            prompt = prompt_template.replace("{chunk}", chunk.content)
            tasks.append(self._execute_chunk(chunk, prompt, executor_fn))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful = []
        errors = []

        for chunk, result in zip(chunks, results):
            if isinstance(result, Exception):
                chunk.error = str(result)
                errors.append({"chunk": chunk.index, "error": str(result)})
            else:
                chunk.result = result
                chunk.processed = True
                successful.append(result)

        # Aggregate
        if aggregate_fn and successful:
            final_result = aggregate_fn(successful)
        else:
            final_result = successful

        return {
            "success": len(errors) == 0,
            "total_chunks": len(chunks),
            "successful_chunks": len(successful),
            "failed_chunks": len(errors),
            "result": final_result,
            "errors": errors,
            "chunks": [c.to_dict() for c in chunks],
        }

    async def _execute_chunk(
        self,
        chunk: TaskChunk,
        prompt: str,
        executor_fn,
    ) -> Any:
        """تنفيذ جزء واحد."""
        async with self._semaphore:
            try:
                result = await executor_fn(prompt)
                chunk.processed_at = datetime.utcnow()
                return result
            except Exception as e:
                logger.error(f"Chunk {chunk.index} failed: {e}")
                raise

    @staticmethod
    def concatenate_results(results: List[str]) -> str:
        """تجميع بالربط."""
        return "\n\n".join(results)

    @staticmethod
    def summarize_results(results: List[str]) -> str:
        """تجميع بالتلخيص."""
        return "\n".join(f"- {r[:200]}..." if len(r) > 200 else f"- {r}" for r in results)
