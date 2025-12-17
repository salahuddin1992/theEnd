"""
Web Dashboard Application - تطبيق واجهة الويب
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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

        except Exception as e:
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
                "last_heartbeat": datetime.utcnow().isoformat(),
            },
            "worker-2": {
                "worker_id": "worker-2",
                "hostname": "node-2.local",
                "status": "ready",
                "resources": {"cpu_cores": 16, "memory_mb": 32768, "gpu_count": 2},
                "current_usage": {"cpu_percent": 78.5, "memory_percent": 45.3},
                "jobs_running": 4,
                "last_heartbeat": datetime.utcnow().isoformat(),
            },
            "worker-3": {
                "worker_id": "worker-3",
                "hostname": "node-3.local",
                "status": "busy",
                "resources": {"cpu_cores": 4, "memory_mb": 8192, "gpu_count": 0},
                "current_usage": {"cpu_percent": 92.1, "memory_percent": 88.7},
                "jobs_running": 1,
                "last_heartbeat": datetime.utcnow().isoformat(),
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
        await self.manager.broadcast({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })


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
        return templates.TemplateResponse("index.html", {
            "request": request,
            "stats": dash.get_stats(),
            "workers": dash.get_workers(),
            "jobs": dash.get_jobs(),
        })

    # صفحة العمال
    @app.get("/workers", response_class=HTMLResponse)
    async def workers_page(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return templates.TemplateResponse("workers.html", {
            "request": request,
            "workers": dash.get_workers(),
        })

    # صفحة المهام
    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs_page(request: Request):
        dash = app.state.dashboard
        await dash.fetch_from_master()
        return templates.TemplateResponse("jobs.html", {
            "request": request,
            "jobs": dash.get_jobs(),
        })

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

    # WebSocket للتحديثات الحية
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        dash = app.state.dashboard
        await dash.manager.connect(websocket)
        try:
            while True:
                # إرسال تحديثات كل 2 ثانية
                await dash.fetch_from_master()
                await websocket.send_json({
                    "type": "update",
                    "stats": dash.get_stats(),
                    "workers": dash.get_workers(),
                    "jobs": dash.get_jobs(),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                await asyncio.sleep(2)
        except WebSocketDisconnect:
            dash.manager.disconnect(websocket)

    return app
