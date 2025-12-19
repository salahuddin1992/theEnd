"""
API Client for communicating with NebulaCompute Master Server
عميل API للتواصل مع خادم الحوسبة الموزعة
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Optional

import httpx
import websockets
from PySide6.QtCore import QObject, Signal


@dataclass
class ClusterStats:
    """Cluster statistics"""

    total_workers: int = 0
    active_workers: int = 0
    total_jobs: int = 0
    running_jobs: int = 0
    pending_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    total_cpu: float = 0.0
    used_cpu: float = 0.0
    total_memory: int = 0
    used_memory: int = 0
    total_gpu: int = 0
    used_gpu: int = 0


class APIClient(QObject):
    """Async API client for master server communication"""

    # Signals for real-time updates
    connected = Signal()
    disconnected = Signal()
    error_occurred = Signal(str)
    stats_updated = Signal(object)
    workers_updated = Signal(list)
    jobs_updated = Signal(list)
    job_status_changed = Signal(str, str)  # job_id, new_status

    def __init__(self, base_url: str = "http://localhost:8765", token: Optional[str] = None):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.ws_url = base_url.replace("http", "ws") + "/ws"
        self.token = token
        self._client: Optional[httpx.AsyncClient] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def headers(self) -> dict:
        """Get request headers with auth token"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def connect(self) -> bool:
        """Connect to master server"""
        try:
            self._client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=30.0)
            # Test connection
            response = await self._client.get("/health")
            if response.status_code == 200:
                self._running = True
                self.connected.emit()
                return True
            return False
        except Exception as e:
            self.error_occurred.emit(f"Connection failed: {str(e)}")
            return False

    async def disconnect(self):
        """Disconnect from master server"""
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._client:
            await self._client.aclose()
        self.disconnected.emit()

    async def start_websocket(self):
        """Start WebSocket connection for real-time updates"""
        self._ws_task = asyncio.create_task(self._websocket_loop())

    async def _websocket_loop(self):
        """WebSocket event loop"""
        while self._running:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    async for message in ws:
                        await self._handle_ws_message(message)
            except websockets.ConnectionClosed:
                if self._running:
                    await asyncio.sleep(5)  # Reconnect delay
            except Exception as e:
                self.error_occurred.emit(f"WebSocket error: {str(e)}")
                if self._running:
                    await asyncio.sleep(5)

    async def _handle_ws_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            event_type = data.get("type")

            if event_type == "stats_update":
                self.stats_updated.emit(data.get("data"))
            elif event_type == "worker_update":
                self.workers_updated.emit(data.get("data", []))
            elif event_type == "job_update":
                self.jobs_updated.emit(data.get("data", []))
            elif event_type == "job_status_changed":
                self.job_status_changed.emit(data.get("job_id"), data.get("status"))
        except json.JSONDecodeError:
            pass

    # ============ Dashboard API ============

    async def get_stats(self) -> ClusterStats:
        """Get cluster statistics"""
        try:
            response = await self._client.get("/api/dashboard/stats")
            if response.status_code == 200:
                data = response.json()
                return ClusterStats(**data)
        except Exception as e:
            self.error_occurred.emit(f"Failed to get stats: {str(e)}")
        return ClusterStats()

    async def get_health(self) -> dict:
        """Get cluster health status"""
        try:
            response = await self._client.get("/health")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get health: {str(e)}")
        return {"status": "unknown"}

    # ============ Workers API ============

    async def get_workers(self) -> list:
        """Get all workers"""
        try:
            response = await self._client.get("/api/workers")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get workers: {str(e)}")
        return []

    async def get_worker(self, worker_id: str) -> Optional[dict]:
        """Get specific worker details"""
        try:
            response = await self._client.get(f"/api/workers/{worker_id}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get worker: {str(e)}")
        return None

    async def drain_worker(self, worker_id: str) -> bool:
        """Drain a worker (stop accepting new jobs)"""
        try:
            response = await self._client.post(f"/api/workers/{worker_id}/drain")
            return response.status_code == 200
        except Exception as e:
            self.error_occurred.emit(f"Failed to drain worker: {str(e)}")
            return False

    async def undrain_worker(self, worker_id: str) -> bool:
        """Undrain a worker"""
        try:
            response = await self._client.post(f"/api/workers/{worker_id}/undrain")
            return response.status_code == 200
        except Exception as e:
            self.error_occurred.emit(f"Failed to undrain worker: {str(e)}")
            return False

    # ============ Jobs API ============

    async def get_jobs(self, status: Optional[str] = None, limit: int = 100) -> list:
        """Get jobs list"""
        try:
            params = {"limit": limit}
            if status:
                params["status"] = status
            response = await self._client.get("/api/jobs", params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get jobs: {str(e)}")
        return []

    async def get_job(self, job_id: str) -> Optional[dict]:
        """Get specific job details"""
        try:
            response = await self._client.get(f"/api/jobs/{job_id}")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get job: {str(e)}")
        return None

    async def submit_job(self, job_spec: dict) -> Optional[str]:
        """Submit a new job"""
        try:
            response = await self._client.post("/api/jobs", json=job_spec)
            if response.status_code in (200, 201):
                data = response.json()
                return data.get("job_id")
        except Exception as e:
            self.error_occurred.emit(f"Failed to submit job: {str(e)}")
        return None

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        try:
            response = await self._client.post(f"/api/jobs/{job_id}/cancel")
            return response.status_code == 200
        except Exception as e:
            self.error_occurred.emit(f"Failed to cancel job: {str(e)}")
            return False

    async def retry_job(self, job_id: str) -> bool:
        """Retry a failed job"""
        try:
            response = await self._client.post(f"/api/jobs/{job_id}/retry")
            return response.status_code == 200
        except Exception as e:
            self.error_occurred.emit(f"Failed to retry job: {str(e)}")
            return False

    async def get_job_logs(self, job_id: str) -> str:
        """Get job logs"""
        try:
            response = await self._client.get(f"/api/jobs/{job_id}/logs")
            if response.status_code == 200:
                data = response.json()
                return data.get("logs", "")
        except Exception as e:
            self.error_occurred.emit(f"Failed to get job logs: {str(e)}")
        return ""

    # ============ Templates API ============

    async def get_templates(self) -> list:
        """Get job templates"""
        try:
            response = await self._client.get("/api/templates")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get templates: {str(e)}")
        return []

    async def create_template(self, template: dict) -> bool:
        """Create a job template"""
        try:
            response = await self._client.post("/api/templates", json=template)
            return response.status_code in (200, 201)
        except Exception as e:
            self.error_occurred.emit(f"Failed to create template: {str(e)}")
            return False

    # ============ Pools API ============

    async def get_pools(self) -> list:
        """Get worker pools"""
        try:
            response = await self._client.get("/api/pools")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get pools: {str(e)}")
        return []

    # ============ Queues API ============

    async def get_queues(self) -> list:
        """Get priority queues"""
        try:
            response = await self._client.get("/api/queues")
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            self.error_occurred.emit(f"Failed to get queues: {str(e)}")
        return []
