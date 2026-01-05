"""
Model Serving - خدمة النماذج
============================

ML model serving endpoints for real-time and batch inference.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from queue import Queue
from threading import Lock
from typing import Any, Dict, List, Optional

from .models import Model

logger = logging.getLogger(__name__)


class EndpointState(str, Enum):
    """Endpoint lifecycle states."""
    CREATING = "creating"
    READY = "ready"
    UPDATING = "updating"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ServingConfig:
    """Model serving configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 4
    max_batch_size: int = 32
    batch_timeout_ms: int = 100
    request_timeout_ms: int = 5000

    # Scaling
    min_replicas: int = 1
    max_replicas: int = 10
    target_concurrency: int = 100

    # Health checks
    health_check_path: str = "/health"
    readiness_check_path: str = "/ready"

    # Metrics
    enable_metrics: bool = True
    metrics_path: str = "/metrics"


@dataclass
class InferenceRequest:
    """Inference request."""
    request_id: str
    model_id: str
    inputs: Any
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    version_id: Optional[str] = None
    priority: int = 0

    # Tracing
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    @classmethod
    def create(cls, model_id: str, inputs: Any, **kwargs) -> InferenceRequest:
        return cls(
            request_id=str(uuid.uuid4()),
            model_id=model_id,
            inputs=inputs,
            **kwargs,
        )


@dataclass
class InferenceResponse:
    """Inference response."""
    request_id: str
    model_id: str
    version_id: str
    predictions: List[Any]

    # Performance
    latency_ms: float = 0.0
    queue_time_ms: float = 0.0
    inference_time_ms: float = 0.0

    # Status
    success: bool = True
    error: Optional[str] = None

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_id": self.model_id,
            "version_id": self.version_id,
            "predictions": self.predictions,
            "latency_ms": self.latency_ms,
            "queue_time_ms": self.queue_time_ms,
            "inference_time_ms": self.inference_time_ms,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class RequestBatcher:
    """Batches inference requests for efficient processing."""

    def __init__(
        self,
        max_batch_size: int = 32,
        timeout_ms: int = 100,
    ):
        self.max_batch_size = max_batch_size
        self.timeout_ms = timeout_ms
        self._queue: Queue = Queue()
        self._lock = Lock()

    def add(self, request: InferenceRequest) -> None:
        """Add request to batch."""
        self._queue.put(request)

    def get_batch(self) -> List[InferenceRequest]:
        """Get a batch of requests."""
        batch = []
        timeout = self.timeout_ms / 1000

        while len(batch) < self.max_batch_size:
            try:
                request = self._queue.get(timeout=timeout)
                batch.append(request)
            except Exception:
                break

        return batch


class ModelEndpoint:
    """
    Model serving endpoint.

    Handles inference requests for a specific model.
    """

    def __init__(
        self,
        endpoint_id: str,
        model: Model,
        version_id: str,
        config: Optional[ServingConfig] = None,
    ):
        self.endpoint_id = endpoint_id
        self.model = model
        self.version_id = version_id
        self.config = config or ServingConfig()

        self._state = EndpointState.CREATING
        self._batcher = RequestBatcher(
            max_batch_size=self.config.max_batch_size,
            timeout_ms=self.config.batch_timeout_ms,
        )
        self._executor = ThreadPoolExecutor(max_workers=self.config.workers)
        self._stats = EndpointStats()
        self._lock = Lock()

    @property
    def state(self) -> EndpointState:
        return self._state

    def start(self) -> None:
        """Start the endpoint."""
        if not self.model.is_loaded:
            raise RuntimeError("Model not loaded")

        self._state = EndpointState.READY
        logger.info(f"Started endpoint {self.endpoint_id}")

    def stop(self) -> None:
        """Stop the endpoint."""
        self._state = EndpointState.DRAINING
        self._executor.shutdown(wait=True)
        self._state = EndpointState.STOPPED
        logger.info(f"Stopped endpoint {self.endpoint_id}")

    def predict(self, request: InferenceRequest) -> InferenceResponse:
        """Handle single inference request."""
        start_time = time.time()

        if self._state != EndpointState.READY:
            return InferenceResponse(
                request_id=request.request_id,
                model_id=request.model_id,
                version_id=self.version_id,
                predictions=[],
                success=False,
                error=f"Endpoint not ready: {self._state.value}",
            )

        try:
            self._stats.requests += 1

            # Run inference
            inference_start = time.time()
            result = self.model.predict(request.inputs, request.request_id)
            inference_time = (time.time() - inference_start) * 1000

            self._stats.successful += 1
            total_time = (time.time() - start_time) * 1000

            return InferenceResponse(
                request_id=request.request_id,
                model_id=request.model_id,
                version_id=self.version_id,
                predictions=result.predictions,
                latency_ms=total_time,
                inference_time_ms=inference_time,
            )

        except Exception as e:
            self._stats.failed += 1
            logger.error(f"Inference error: {e}")

            return InferenceResponse(
                request_id=request.request_id,
                model_id=request.model_id,
                version_id=self.version_id,
                predictions=[],
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    async def predict_async(self, request: InferenceRequest) -> InferenceResponse:
        """Async inference request."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.predict,
            request,
        )

    def predict_batch(
        self,
        requests: List[InferenceRequest],
    ) -> List[InferenceResponse]:
        """Handle batch inference requests."""
        responses = []

        for request in requests:
            response = self.predict(request)
            responses.append(response)

        return responses

    def get_stats(self) -> Dict[str, Any]:
        """Get endpoint statistics."""
        return self._stats.to_dict()

    def is_healthy(self) -> bool:
        """Check if endpoint is healthy."""
        return self._state == EndpointState.READY

    def is_ready(self) -> bool:
        """Check if endpoint is ready for traffic."""
        return self._state == EndpointState.READY and self.model.is_loaded


@dataclass
class EndpointStats:
    """Endpoint statistics."""
    requests: int = 0
    successful: int = 0
    failed: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.successful / self.requests

    @property
    def avg_latency_ms(self) -> float:
        if self.successful == 0:
            return 0.0
        return self.total_latency_ms / self.successful

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests": self.requests,
            "successful": self.successful,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }


@dataclass
class BatchInferenceJob:
    """Batch inference job for processing large datasets."""
    job_id: str
    model_id: str
    version_id: str

    # Input/Output
    input_path: str
    output_path: str
    input_format: str = "csv"  # csv, parquet, json
    output_format: str = "csv"

    # Processing config
    batch_size: int = 1000
    max_workers: int = 4
    shuffle: bool = False

    # Status
    state: str = "pending"
    progress: float = 0.0
    records_processed: int = 0
    records_failed: int = 0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error handling
    error: Optional[str] = None
    failed_records_path: Optional[str] = None


class BatchInferenceRunner:
    """Runs batch inference jobs."""

    def __init__(self, model: Model, version_id: str):
        self.model = model
        self.version_id = version_id
        self._running_jobs: Dict[str, BatchInferenceJob] = {}

    async def run(self, job: BatchInferenceJob) -> BatchInferenceJob:
        """Run a batch inference job."""
        import pandas as pd

        job.state = "running"
        job.started_at = datetime.now(timezone.utc)
        self._running_jobs[job.job_id] = job

        try:
            # Load input data
            if job.input_format == "csv":
                df = pd.read_csv(job.input_path)
            elif job.input_format == "parquet":
                df = pd.read_parquet(job.input_path)
            elif job.input_format == "json":
                df = pd.read_json(job.input_path)
            else:
                raise ValueError(f"Unsupported input format: {job.input_format}")

            total_records = len(df)
            results = []

            # Process in batches
            for i in range(0, total_records, job.batch_size):
                batch_df = df.iloc[i:i + job.batch_size]
                batch_inputs = batch_df.to_dict(orient="records")

                try:
                    for inputs in batch_inputs:
                        result = self.model.predict(inputs)
                        results.append(result.predictions[0])
                        job.records_processed += 1
                except Exception as e:
                    job.records_failed += len(batch_inputs) - len(results) % job.batch_size
                    logger.error(f"Batch processing error: {e}")

                job.progress = job.records_processed / total_records

            # Save results
            results_df = pd.DataFrame({"prediction": results})
            if job.output_format == "csv":
                results_df.to_csv(job.output_path, index=False)
            elif job.output_format == "parquet":
                results_df.to_parquet(job.output_path, index=False)
            elif job.output_format == "json":
                results_df.to_json(job.output_path, orient="records")

            job.state = "completed"
            job.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            job.state = "failed"
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(f"Batch job {job.job_id} failed: {e}")

        finally:
            del self._running_jobs[job.job_id]

        return job


class ModelServer:
    """
    Model Server - خادم النماذج.

    Central server for managing multiple model endpoints.
    """

    def __init__(self, config: Optional[ServingConfig] = None):
        self.config = config or ServingConfig()
        self._endpoints: Dict[str, ModelEndpoint] = {}
        self._models: Dict[str, Model] = {}
        self._lock = Lock()
        self._running = False

    def start(self) -> None:
        """Start the model server."""
        self._running = True
        logger.info(f"Model server started on {self.config.host}:{self.config.port}")

    def stop(self) -> None:
        """Stop the model server."""
        self._running = False

        for endpoint in self._endpoints.values():
            endpoint.stop()

        logger.info("Model server stopped")

    def register_model(self, model: Model) -> None:
        """Register a model."""
        with self._lock:
            self._models[model.model_id] = model
            logger.info(f"Registered model: {model.model_id}")

    def unregister_model(self, model_id: str) -> None:
        """Unregister a model."""
        with self._lock:
            if model_id in self._models:
                del self._models[model_id]
                logger.info(f"Unregistered model: {model_id}")

    def create_endpoint(
        self,
        endpoint_id: str,
        model_id: str,
        version_id: str,
        artifact_path: str,
    ) -> ModelEndpoint:
        """Create a new endpoint for a model."""
        with self._lock:
            if model_id not in self._models:
                raise ValueError(f"Model not registered: {model_id}")

            model = self._models[model_id]

            # Load model if not loaded
            if not model.is_loaded:
                model.load(artifact_path)

            # Create endpoint
            endpoint = ModelEndpoint(
                endpoint_id=endpoint_id,
                model=model,
                version_id=version_id,
                config=self.config,
            )
            endpoint.start()

            self._endpoints[endpoint_id] = endpoint
            logger.info(f"Created endpoint: {endpoint_id}")

            return endpoint

    def delete_endpoint(self, endpoint_id: str) -> None:
        """Delete an endpoint."""
        with self._lock:
            if endpoint_id in self._endpoints:
                self._endpoints[endpoint_id].stop()
                del self._endpoints[endpoint_id]
                logger.info(f"Deleted endpoint: {endpoint_id}")

    def get_endpoint(self, endpoint_id: str) -> Optional[ModelEndpoint]:
        """Get an endpoint by ID."""
        return self._endpoints.get(endpoint_id)

    def list_endpoints(self) -> List[str]:
        """List all endpoint IDs."""
        return list(self._endpoints.keys())

    def predict(
        self,
        endpoint_id: str,
        request: InferenceRequest,
    ) -> InferenceResponse:
        """Run inference on an endpoint."""
        endpoint = self._endpoints.get(endpoint_id)
        if not endpoint:
            return InferenceResponse(
                request_id=request.request_id,
                model_id=request.model_id,
                version_id="",
                predictions=[],
                success=False,
                error=f"Endpoint not found: {endpoint_id}",
            )

        return endpoint.predict(request)

    async def predict_async(
        self,
        endpoint_id: str,
        request: InferenceRequest,
    ) -> InferenceResponse:
        """Async inference."""
        endpoint = self._endpoints.get(endpoint_id)
        if not endpoint:
            return InferenceResponse(
                request_id=request.request_id,
                model_id=request.model_id,
                version_id="",
                predictions=[],
                success=False,
                error=f"Endpoint not found: {endpoint_id}",
            )

        return await endpoint.predict_async(request)

    def get_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        return {
            "running": self._running,
            "endpoints": len(self._endpoints),
            "models": len(self._models),
            "endpoint_stats": {
                eid: ep.get_stats()
                for eid, ep in self._endpoints.items()
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy" if self._running else "unhealthy",
            "endpoints": {
                eid: ep.is_healthy()
                for eid, ep in self._endpoints.items()
            },
        }
