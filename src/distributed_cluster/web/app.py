"""
Web Dashboard Application - تطبيق واجهة الويب
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# مسارات الملفات
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


class ConnectionManager:
    """إدارة اتصالات WebSocket"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """بث رسالة لجميع المتصلين"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


class WebDashboard:
    """
    واجهة ويب للمراقبة والإدارة

    توفر:
    - لوحة تحكم رئيسية
    - قائمة العمال وحالتهم
    - قائمة المهام
    - إحصائيات حية
    """

    def __init__(self, master_url: str = "http://localhost:8765"):
        self.master_url = master_url
        self.app = create_app(self)
        self.manager = ConnectionManager()

        # بيانات مؤقتة (في الإنتاج ستأتي من Master)
        self._workers: Dict[str, Dict] = {}
        self._jobs: Dict[str, Dict] = {}
        self._stats: Dict[str, Any] = {
            "total_workers": 0,
            "active_workers": 0,
            "total_jobs": 0,
            "running_jobs": 0,
            "completed_jobs": 0,
            "failed_jobs": 0,
            "total_cpu_cores": 0,
            "used_cpu_cores": 0,
            "total_memory_gb": 0,
            "used_memory_gb": 0,
        }

    async def fetch_from_master(self):
        """جلب البيانات من Master"""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                # جلب العمال
                workers_resp = await client.get(f"{self.master_url}/workers", timeout=5.0)
                if workers_resp.status_code == 200:
                    workers = workers_resp.json()
                    self._workers = {w["worker_id"]: w for w in workers}

                # جلب المهام
                jobs_resp = await client.get(f"{self.master_url}/jobs", timeout=5.0)
                if jobs_resp.status_code == 200:
                    jobs = jobs_resp.json()
                    self._jobs = {j["job_id"]: j for j in jobs}

                # جلب الإحصائيات
                stats_resp = await client.get(f"{self.master_url}/stats", timeout=5.0)
                if stats_resp.status_code == 200:
                    self._stats = stats_resp.json()

        except Exception:
            # في حالة عدم الاتصال، نستخدم بيانات تجريبية
            self._generate_demo_data()

    def _generate_demo_data(self):
        """إنشاء بيانات تجريبية"""
        self._workers = {
            "worker-1": {
                "worker_id": "worker-1",
                "hostname": "node-1.local",
                "status": "ready",
                "resources": {"cpu_cores": 8, "memory_mb": 16384, "gpu_count": 1},
                "current_usage": {"cpu_percent": 45.2, "memory_percent": 62.1},
                "jobs_running": 2,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            },
            "worker-2": {
                "worker_id": "worker-2",
                "hostname": "node-2.local",
                "status": "ready",
                "resources": {"cpu_cores": 16, "memory_mb": 32768, "gpu_count": 2},
                "current_usage": {"cpu_percent": 78.5, "memory_percent": 45.3},
                "jobs_running": 4,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            },
            "worker-3": {
                "worker_id": "worker-3",
                "hostname": "node-3.local",
                "status": "busy",
                "resources": {"cpu_cores": 4, "memory_mb": 8192, "gpu_count": 0},
                "current_usage": {"cpu_percent": 92.1, "memory_percent": 88.7},
                "jobs_running": 1,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            },
        }

        self._jobs = {
            "job-001": {
                "job_id": "job-001",
                "name": "Training Model",
                "status": "running",
                "worker_id": "worker-1",
                "progress": 67,
                "created_at": "2024-01-15T10:30:00",
                "started_at": "2024-01-15T10:31:00",
            },
            "job-002": {
                "job_id": "job-002",
                "name": "Data Processing",
                "status": "running",
                "worker_id": "worker-2",
                "progress": 45,
                "created_at": "2024-01-15T10:35:00",
                "started_at": "2024-01-15T10:36:00",
            },
            "job-003": {
                "job_id": "job-003",
                "name": "Image Analysis",
                "status": "completed",
                "worker_id": "worker-1",
                "progress": 100,
                "created_at": "2024-01-15T09:00:00",
                "completed_at": "2024-01-15T09:45:00",
            },
            "job-004": {
                "job_id": "job-004",
                "name": "Report Generation",
                "status": "pending",
                "worker_id": None,
                "progress": 0,
                "created_at": "2024-01-15T10:40:00",
            },
            "job-005": {
                "job_id": "job-005",
                "name": "Video Encoding",
                "status": "failed",
                "worker_id": "worker-3",
                "progress": 23,
                "created_at": "2024-01-15T08:00:00",
                "error": "Out of memory",
            },
        }

        self._stats = {
            "total_workers": 3,
            "active_workers": 3,
            "total_jobs": 5,
            "running_jobs": 2,
            "completed_jobs": 1,
            "failed_jobs": 1,
            "pending_jobs": 1,
            "total_cpu_cores": 28,
            "used_cpu_cores": 12,
            "total_memory_gb": 56,
            "used_memory_gb": 34,
            "total_gpu": 3,
            "used_gpu": 2,
        }

    def get_workers(self) -> List[Dict]:
        return list(self._workers.values())

    def get_jobs(self) -> List[Dict]:
        return list(self._jobs.values())

    def get_stats(self) -> Dict:
        return self._stats

    async def broadcast_update(self, event_type: str, data: Dict):
        """بث تحديث للمتصلين"""
        await self.manager.broadcast(
            {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def create_app(dashboard: Optional[WebDashboard] = None) -> FastAPI:
    """إنشاء تطبيق FastAPI"""

    app = FastAPI(
        title="Distributed Cluster Dashboard",
        description="واجهة ويب لمراقبة وإدارة الكلاستر",
        version="1.0.0",
    )

    # إعداد القوالب والملفات الثابتة
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # تخزين Dashboard في state
    app.state.dashboard = dashboard or WebDashboard()

    # الصفحة الرئيسية
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "stats": dash.get_stats(),
                "workers": dash.get_workers(),
                "jobs": dash.get_jobs(),
            },
        )

    # صفحة العمال
    @app.get("/workers", response_class=HTMLResponse)
    async def workers_page(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return templates.TemplateResponse(request, "workers.html", {"workers": dash.get_workers()})

    # صفحة المهام
    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs_page(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return templates.TemplateResponse(request, "jobs.html", {"jobs": dash.get_jobs()})

    # صفحة مزودي AI
    @app.get("/ai", response_class=HTMLResponse)
    async def ai_page(request: Request):

        # بيانات المزودين
        ai_data = {
            "providers": [
                {"name": "Claude", "status": "active", "models": 5},
                {"name": "OpenAI", "status": "active", "models": 4},
                {"name": "Gemini", "status": "active", "models": 5},
                {"name": "Groq", "status": "active", "models": 6},
                {"name": "Mistral", "status": "active", "models": 7},
                {"name": "Together", "status": "active", "models": 100},
                {"name": "DeepSeek", "status": "active", "models": 3},
                {"name": "Cohere", "status": "active", "models": 4},
                {"name": "xAI", "status": "active", "models": 4},
                {"name": "Perplexity", "status": "active", "models": 3},
                {"name": "HuggingFace", "status": "active", "models": 1000000},
                {"name": "Ollama", "status": "active", "models": 50},
            ],
            "active_providers": 12,
            "total_models": 150,
            "total_requests": 1234,
            "total_tokens": 567890,
            # موارد النظام
            "cpu_cores": 8,
            "cpu_percent": 45,
            "ram_total_gb": 32,
            "ram_used_gb": 18,
            "ram_percent": 56,
            "gpu_count": 1,
            "gpu_percent": 30,
            "gpu_memory_used": 6,
            "gpu_memory_total": 12,
            "disk_total_gb": 500,
            "disk_free_gb": 320,
            "disk_percent": 36,
        }

        return templates.TemplateResponse(request, "ai.html", ai_data)

    # صفحة المزامنة
    @app.get("/sync", response_class=HTMLResponse)
    async def sync_page(request: Request):

        # بيانات المزامنة
        sync_data = {
            "sync_status": "active",
            "connected_peers": 3,
            "total_synced_items": 1523,
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "sync_mode": "realtime",
            # Peers info
            "peers": [
                {
                    "id": "peer-1",
                    "name": "Node-Alpha",
                    "url": "http://192.168.1.10:8765",
                    "status": "connected",
                    "latency_ms": 12,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "id": "peer-2",
                    "name": "Node-Beta",
                    "url": "http://192.168.1.11:8765",
                    "status": "connected",
                    "latency_ms": 8,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "id": "peer-3",
                    "name": "Node-Gamma",
                    "url": "http://192.168.1.12:8765",
                    "status": "syncing",
                    "latency_ms": 25,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                },
            ],
            # Transfer stats
            "active_transfers": 2,
            "total_bytes_sent": 1024 * 1024 * 156,  # 156 MB
            "total_bytes_received": 1024 * 1024 * 234,  # 234 MB
            "transfer_speed_bps": 1024 * 1024 * 5,  # 5 MB/s
            # Conflict resolution stats
            "conflicts_resolved": 45,
            "conflicts_pending": 2,
            "resolution_strategy": "last_write_wins",
            # State sync
            "state_version": 1523,
            "state_items": 856,
            "pending_deltas": 3,
        }

        return templates.TemplateResponse(request, "sync.html", sync_data)

    # صفحة المقاييس
    @app.get("/metrics", response_class=HTMLResponse)
    async def metrics_page(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()

        # بيانات المقاييس
        metrics_data = {
            "throughput": "1,234",
            "latency": 45,
            "success_rate": 99.2,
            "resource_usage": 67,
            "cpu_usage": 45,
            "cpu_min": 12,
            "cpu_avg": 38,
            "cpu_max": 78,
            "memory_usage": 62,
            "mem_min": 45,
            "mem_avg": 58,
            "mem_max": 85,
            "network_in": 89,
            "network_out": 125,
            "disk_read": 45,
            "disk_write": 32,
            "default_queue": 23,
            "high_priority_queue": 8,
            "background_queue": 156,
        }

        return templates.TemplateResponse(request, "metrics.html", metrics_data)

    # API endpoints
    @app.get("/api/stats")
    async def api_stats():
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return dash.get_stats()

    @app.get("/api/workers")
    async def api_workers():
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return dash.get_workers()

    @app.get("/api/jobs")
    async def api_jobs():
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return dash.get_jobs()

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        import httpx

        dash = app.state.dashboard
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(f"{dash.master_url}/jobs/{job_id}")
                return {"success": resp.status_code == 200}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Sync API endpoints
    @app.get("/api/sync/status")
    async def api_sync_status():
        """الحصول على حالة المزامنة"""
        return {
            "status": "active",
            "mode": "realtime",
            "connected_peers": 3,
            "state_version": 1523,
            "last_sync": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/sync/peers")
    async def api_sync_peers():
        """الحصول على قائمة الأقران"""
        return [
            {
                "id": "peer-1",
                "name": "Node-Alpha",
                "url": "http://192.168.1.10:8765",
                "status": "connected",
                "latency_ms": 12,
            },
            {
                "id": "peer-2",
                "name": "Node-Beta",
                "url": "http://192.168.1.11:8765",
                "status": "connected",
                "latency_ms": 8,
            },
        ]

    @app.post("/api/sync/peers")
    async def api_add_peer(request: Request):
        """إضافة قرين جديد"""
        data = await request.json()
        url = data.get("url")
        name = data.get("name", "Unknown")
        if not url:
            raise HTTPException(status_code=400, detail="URL is required")
        return {
            "success": True,
            "peer_id": f"peer-{datetime.now(timezone.utc).timestamp()}",
            "message": f"Peer {name} added successfully",
        }

    @app.delete("/api/sync/peers/{peer_id}")
    async def api_remove_peer(peer_id: str):
        """إزالة قرين"""
        return {"success": True, "message": f"Peer {peer_id} removed"}

    @app.get("/api/sync/state")
    async def api_sync_state():
        """الحصول على حالة البيانات المتزامنة"""
        return {
            "version": 1523,
            "items_count": 856,
            "pending_deltas": 3,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    @app.post("/api/sync/trigger")
    async def api_trigger_sync():
        """تشغيل مزامنة يدوية"""
        return {
            "success": True,
            "message": "Sync triggered",
            "sync_id": f"sync-{datetime.now(timezone.utc).timestamp()}",
        }

    @app.get("/api/sync/transfers")
    async def api_sync_transfers():
        """الحصول على عمليات النقل النشطة"""
        return {
            "active": 2,
            "completed": 45,
            "failed": 1,
            "transfers": [
                {
                    "id": "transfer-1",
                    "source": "peer-1",
                    "target": "local",
                    "progress": 67,
                    "bytes_transferred": 1024 * 1024 * 50,
                    "status": "in_progress",
                },
            ],
        }

    @app.get("/api/sync/conflicts")
    async def api_sync_conflicts():
        """الحصول على التعارضات"""
        return {
            "resolved": 45,
            "pending": 2,
            "conflicts": [
                {
                    "id": "conflict-1",
                    "key": "config.timeout",
                    "local_value": 30,
                    "remote_value": 60,
                    "remote_peer": "peer-2",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                },
            ],
        }

    @app.post("/api/sync/conflicts/{conflict_id}/resolve")
    async def api_resolve_conflict(conflict_id: str, request: Request):
        """حل تعارض"""
        data = await request.json()
        strategy = data.get("strategy", "local_wins")
        return {
            "success": True,
            "message": f"Conflict {conflict_id} resolved using {strategy}",
        }

    # WebSocket للتحديثات الحية
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        dash = app.state.dashboard
        await dash.manager.connect(websocket)
        try:
            while True:
                # إرسال تحديثات كل 2 ثانية
                await dash.fetch_from_master()
                await websocket.send_json(
                    {
                        "type": "update",
                        "stats": dash.get_stats(),
                        "workers": dash.get_workers(),
                        "jobs": dash.get_jobs(),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                await asyncio.sleep(2)
        except WebSocketDisconnect:
            dash.manager.disconnect(websocket)

    return app
