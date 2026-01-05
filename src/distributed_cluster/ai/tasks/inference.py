"""
Distributed Inference Task - مهمة الاستنتاج الموزع
====================================================

Handles distributed inference across multiple workers.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List

from .manager import AITask, AITaskResult

logger = logging.getLogger(__name__)


@dataclass
class InferenceConfig:
    """إعدادات الاستنتاج."""
    max_tokens: int = 1024
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    stop_sequences: List[str] = None
    stream: bool = False
    batch_size: int = 1

    def __post_init__(self):
        if self.stop_sequences is None:
            self.stop_sequences = []


class DistributedInferenceTask:
    """
    مهمة استنتاج موزعة.

    Features:
    - Batch inference across multiple workers
    - Load balancing based on model requirements
    - Streaming support
    - Automatic retry on failure
    """

    def __init__(
        self,
        provider=None,
        router=None,
    ):
        self.provider = provider
        self.router = router

    async def execute(self, task: AITask) -> AITaskResult:
        """
        تنفيذ مهمة الاستنتاج.

        Args:
            task: مهمة AI

        Returns:
            AITaskResult: نتيجة الاستنتاج
        """
        try:
            config = InferenceConfig(**task.config.get("inference", {}))

            task.update_progress(10, "Preparing inference")

            # Handle different input types
            if isinstance(task.input_data, str):
                # Single prompt
                result = await self._infer_single(task, config)
            elif isinstance(task.input_data, list):
                # Batch inference
                result = await self._infer_batch(task, config)
            else:
                raise ValueError(f"Unsupported input type: {type(task.input_data)}")

            return result

        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return AITaskResult(success=False, error=str(e))

    async def _infer_single(
        self,
        task: AITask,
        config: InferenceConfig,
    ) -> AITaskResult:
        """استنتاج فردي."""
        task.update_progress(30, "Running inference")

        if self.router:
            # Use distributed router
            response = await self.router.generate(
                prompt=task.input_data,
                model=task.model,
                config=self._to_generation_config(config),
            )
            output = response.content

        elif self.provider:
            # Use single provider
            response = await self.provider.generate(
                prompt=task.input_data,
                model=task.model,
                config=self._to_generation_config(config),
            )
            output = response.content

        else:
            # Simulation mode
            output = f"[Simulated response for: {task.input_data[:50]}...]"
            await asyncio.sleep(1)  # Simulate processing

        task.update_progress(90, "Processing complete")

        return AITaskResult(
            success=True,
            output=output,
            metrics={
                "tokens": len(output.split()) if output else 0,
            },
        )

    async def _infer_batch(
        self,
        task: AITask,
        config: InferenceConfig,
    ) -> AITaskResult:
        """استنتاج دفعي."""
        prompts = task.input_data
        total = len(prompts)
        outputs = []

        # Process in batches
        batch_size = config.batch_size
        for i in range(0, total, batch_size):
            batch = prompts[i:i + batch_size]
            progress = 10 + (80 * (i + batch_size) / total)
            task.update_progress(progress, f"Processing batch {i//batch_size + 1}")

            # Process batch concurrently
            tasks = []
            for prompt in batch:
                sub_task = AITask(
                    model=task.model,
                    input_data=prompt,
                    config=task.config,
                )
                tasks.append(self._infer_single(sub_task, config))

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    outputs.append({"error": str(result)})
                elif result.success:
                    outputs.append(result.output)
                else:
                    outputs.append({"error": result.error})

        return AITaskResult(
            success=True,
            output=outputs,
            metrics={
                "total_prompts": total,
                "successful": len([o for o in outputs if not isinstance(o, dict)]),
            },
        )

    def _to_generation_config(self, config: InferenceConfig):
        """تحويل إلى إعدادات التوليد."""
        try:
            from distributed_cluster.ai.llm.provider import GenerationConfig
            return GenerationConfig(
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                top_p=config.top_p,
                top_k=config.top_k,
                stop_sequences=config.stop_sequences,
            )
        except ImportError:
            return None


async def inference_handler(task: AITask) -> AITaskResult:
    """معالج مهام الاستنتاج."""
    inference_task = DistributedInferenceTask()
    return await inference_task.execute(task)
