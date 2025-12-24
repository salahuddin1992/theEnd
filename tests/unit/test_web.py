"""
Tests for Web Dashboard
اختبارات واجهة الويب
"""

import pytest
from fastapi.testclient import TestClient

from distributed_cluster.web.app import ConnectionManager, WebDashboard, create_app


class TestWebDashboard:
    """اختبارات WebDashboard"""

    def test_dashboard_creation(self):
        """اختبار إنشاء Dashboard"""
        dashboard = WebDashboard()
        assert dashboard.master_url == "http://localhost:8765"
        assert dashboard.app is not None

    def test_dashboard_with_custom_master(self):
        """اختبار إنشاء Dashboard بعنوان مخصص"""
        dashboard = WebDashboard(master_url="http://192.168.1.10:8765")
        assert dashboard.master_url == "http://192.168.1.10:8765"

    def test_generate_demo_data(self):
        """اختبار إنشاء بيانات تجريبية"""
        dashboard = WebDashboard()
        dashboard._generate_demo_data()

        workers = dashboard.get_workers()
        assert len(workers) > 0
        assert workers[0]["worker_id"] is not None

        jobs = dashboard.get_jobs()
        assert len(jobs) > 0

        stats = dashboard.get_stats()
        assert "total_workers" in stats
        assert "total_jobs" in stats


class TestConnectionManager:
    """اختبارات ConnectionManager"""

    def test_manager_creation(self):
        """اختبار إنشاء المدير"""
        manager = ConnectionManager()
        assert manager.active_connections == []


class TestFastAPIApp:
    """اختبارات تطبيق FastAPI"""

    @pytest.fixture
    def client(self):
        """إنشاء عميل اختبار"""
        dashboard = WebDashboard()
        dashboard._generate_demo_data()
        return TestClient(dashboard.app)

    def test_index_page(self, client):
        """اختبار الصفحة الرئيسية"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_workers_page(self, client):
        """اختبار صفحة العمال"""
        response = client.get("/workers")
        assert response.status_code == 200

    def test_jobs_page(self, client):
        """اختبار صفحة المهام"""
        response = client.get("/jobs")
        assert response.status_code == 200

    def test_api_stats(self, client):
        """اختبار API الإحصائيات"""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_workers" in data

    def test_api_workers(self, client):
        """اختبار API العمال"""
        response = client.get("/api/workers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_api_jobs(self, client):
        """اختبار API المهام"""
        response = client.get("/api/jobs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCreateApp:
    """اختبارات create_app"""

    def test_create_app_default(self):
        """اختبار إنشاء التطبيق الافتراضي"""
        app = create_app()
        assert app is not None
        assert app.title == "Distributed Cluster Dashboard"

    def test_create_app_with_dashboard(self):
        """اختبار إنشاء التطبيق مع Dashboard"""
        dashboard = WebDashboard(master_url="http://test:8765")
        app = create_app(dashboard)
        assert app.state.dashboard.master_url == "http://test:8765"
