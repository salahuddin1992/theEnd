# نظام الحوسبة الموزّعة | NebulaCompute

نظام حوسبة موزّعة متكامل يتيح توزيع المهام على عدة أجهزة (workers) وإدارتها من نقطة تحكم مركزية (master).

A comprehensive distributed computing system that allows distributing tasks across multiple machines (workers) and managing them from a central control point (master).

## المنصات المدعومة | Supported Platforms

| Platform | Status |
|----------|--------|
| Windows 10/11 | ✅ Full Support |
| Linux (Ubuntu, CentOS, etc.) | ✅ Full Support |
| macOS | ✅ Full Support |

## المفهوم الأساسي | Core Concept

```
                    ┌─────────────────────┐
                    │     Master Node     │
                    │  (Control Plane)    │
                    ├─────────────────────┤
                    │  • REST API         │
                    │  • Scheduler        │
                    │  • State Store      │
                    │  • Health Monitor   │
                    │  • Web Dashboard    │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼────────┐ ┌─────▼─────┐ ┌───────▼───────┐
     │   Worker #1     │ │ Worker #2 │ │   Worker #N   │
     │ CPU: 8, GPU: 1  │ │ CPU: 16   │ │ CPU: 4, GPU:2 │
     └─────────────────┘ └───────────┘ └───────────────┘
```

## الميزات | Features

### الميزات الأساسية
- **توزيع المهام**: إرسال مهام للعمّال وتنفيذها على مواردهم
- **جدولة ذكية**: Bin-packing scheduler يوزع المهام بناءً على الموارد المتاحة (CPU/RAM/GPU)
- **عزل آمن**: تنفيذ المهام داخل Docker containers
- **مراقبة حية**: WebSocket للتحديثات الفورية
- **تحمّل الأخطاء**: إعادة المحاولة التلقائية عند الفشل
- **دعم GPU**: تخصيص GPUs للمهام التي تحتاجها

### الميزات المتقدمة
- **High Availability (HA)**: دعم 3 Masters مع Leader Election
- **Mesh Network**: وضع P2P للحوسبة اللامركزية
- **لوحة تحكم Web**: واجهة ويب تفاعلية مع WebSocket
- **تطبيق Desktop**: تطبيق سطح مكتب (Windows/Linux/macOS)
- **AI/ML Integration**: دعم Ollama, vLLM, OpenAI
- **Security**: JWT Auth, RBAC, Encryption, Audit Logging

## التثبيت | Installation

```bash
# Clone the repository
git clone <repository-url>
cd theEnd

# Install with pip
pip install -e ".[dev]"

# أو باستخدام Conda
conda env create -f environment.yml
conda activate theend-env
```

## الاستخدام السريع | Quick Start

### 1. تشغيل Master

```bash
# تشغيل master على المنفذ 8765
dc-master start --port 8765

# أو مع إعدادات مخصصة
dc-master start --config config/master.example.json
```

### 2. تشغيل Worker(s)

على كل جهاز عامل:

```bash
# الاتصال بـ master
dc-worker start --master http://master-ip:8765

# مع tags للتصنيف
dc-worker start --master http://master-ip:8765 --tags gpu,high-memory

# عرض معلومات الجهاز
dc-worker info
```

### 3. إرسال Jobs

```bash
# إرسال أمر بسيط
dc-submit run "echo hello world"

# إرسال مع متطلبات موارد
dc-submit run "python train.py" --cpu 4 --memory 8192 --gpu 1

# تشغيل داخل Docker
dc-submit run "python script.py" --docker python:3.11

# انتظار النتيجة
dc-submit run "python test.py" --wait

# إرسال مجموعة jobs من ملف
dc-submit batch examples/jobs.example.json
```

### 4. المراقبة

```bash
# حالة الكلاستر
dc-master status

# قائمة workers
dc-master workers

# قائمة jobs
dc-master jobs
dc-submit list --status running

# تفاصيل job
dc-submit status job-abc123

# إلغاء job
dc-submit cancel job-abc123
```

## لوحات التحكم | Dashboards

### لوحة التحكم Web

```bash
# تشغيل لوحة التحكم Web
dc-web start --port 8080

# ثم افتح في المتصفح
# http://localhost:8080
```

**الميزات:**
- إحصائيات الكلاستر في الوقت الفعلي
- إدارة Workers و Jobs
- تحديثات حية عبر WebSocket
- رسوم بيانية للأداء

### تطبيق سطح المكتب

```bash
# تشغيل تطبيق سطح المكتب
dc-desktop

# أو بناء ملف .exe (Windows)
cd src/distributed_cluster/desktop
python build_exe.py
# الملف: dist/NebulaCompute.exe
```

**الميزات:**
- واجهة رسومية كاملة (PySide6)
- إدارة الاتصال بـ Master
- عرض Jobs و Workers
- System Tray integration
- Dark/Light themes

### CLI Dashboard

```bash
# مراقبة حية في Terminal
nebula watch

# الوضع التفاعلي
nebula shell
```

## High Availability (HA)

تشغيل 3 Masters مع failover تلقائي:

```bash
# باستخدام Docker Compose
docker-compose -f docker-compose.ha.yml up

# أو يدوياً
dc-master start --port 8765 --ha-peers master2:8765,master3:8765
```

## Mesh Network (P2P)

وضع الشبكة اللامركزية:

```bash
# تشغيل node
dc-mesh start --port 9000 --bootstrap peer1:9000,peer2:9000

# إرسال job للشبكة
dc-mesh submit "python task.py" --replicas 3
```

## Security

### Authentication

```bash
# إنشاء token للمستخدم
dc-master token create --user admin --role admin

# إنشاء enrollment token لـ worker
dc-master enrollment create --expires 24h
```

### RBAC Roles

| Role | Permissions |
|------|-------------|
| admin | كل الصلاحيات |
| operator | إدارة Jobs و Workers |
| user | إرسال Jobs فقط |
| readonly | مشاهدة فقط |

## API Reference

Master يوفر REST API على المنفذ المحدد:

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/stats` | Cluster statistics |
| POST | `/workers/register` | Register new worker |
| POST | `/workers/heartbeat` | Worker heartbeat |
| GET | `/workers` | List workers |
| POST | `/jobs` | Submit new job |
| GET | `/jobs` | List jobs |
| GET | `/jobs/{id}` | Get job details |
| DELETE | `/jobs/{id}` | Cancel job |
| GET | `/events` | Recent events |
| WS | `/ws` | WebSocket for live updates |

### مثال API

```python
import httpx

# إرسال job
response = httpx.post("http://localhost:8765/jobs", json={
    "command": "python",
    "args": ["-c", "print('Hello!')"],
    "name": "my-job",
    "resources": {
        "cpu_cores": 2.0,
        "memory_mb": 1024,
        "gpu_count": 0,
    },
    "timeout_seconds": 300,
})
job_id = response.json()["job_id"]

# الحصول على النتيجة
job = httpx.get(f"http://localhost:8765/jobs/{job_id}").json()
print(job["status"], job.get("result"))
```

## بنية المشروع | Project Structure

```
distributed_cluster/
├── core/                 # إعدادات وأدوات أساسية
│   ├── config.py         # Configuration classes
│   └── resource_detector.py  # CPU/GPU/RAM detection
├── models/               # Data models
│   ├── resources.py      # ResourceSpec, ResourceUsage
│   ├── worker.py         # WorkerInfo, WorkerStatus
│   ├── job.py            # Job, JobSubmission, JobResult
│   └── events.py         # Event types
├── scheduler/            # Job scheduling
│   └── scheduler.py      # Bin-packing scheduler
├── master/               # Control plane
│   ├── state.py          # Cluster state management
│   └── server.py         # FastAPI server
├── worker/               # Worker agent
│   ├── agent.py          # Worker agent
│   ├── ha_agent.py       # HA multi-master support
│   └── executor.py       # Job executor (process/Docker)
├── web/                  # Web dashboard
│   ├── app.py            # FastAPI web app
│   └── templates/        # HTML templates
├── desktop/              # Desktop application
│   ├── main.py           # Entry point
│   ├── main_window.py    # Main window
│   └── views/            # UI views
├── mesh/                 # P2P mesh network
│   ├── node.py           # Mesh node
│   └── router.py         # Task router
├── security/             # Security & Auth
│   ├── auth.py           # JWT Authentication
│   ├── crypto.py         # Encryption utilities
│   └── secrets.py        # Secrets management
├── ai/                   # AI/ML integration
│   └── llm/              # LLM providers
└── cli/                  # Command-line tools
    ├── master_cli.py     # dc-master
    ├── worker_cli.py     # dc-worker
    ├── submit_cli.py     # dc-submit
    └── mesh_cli.py       # dc-mesh
```

## سياسات الجدولة | Scheduling Policies

- **First-Fit**: أول worker مناسب
- **Best-Fit**: أقل موارد فائضة (bin packing) - الافتراضي
- **Worst-Fit**: أكثر موارد فائضة (spread)
- **Round-Robin**: بالتناوب
- **Least-Loaded**: أقل عدد jobs نشطة

## Docker Deployment

```bash
# Development (single node)
docker-compose -f docker-compose.dev.yml up

# Production (single master)
docker-compose -f docker-compose.prod.yml up

# High Availability (3 masters)
docker-compose -f docker-compose.ha.yml up
```

## متطلبات النظام | Requirements

- Python 3.10+
- Docker (اختياري، لتشغيل jobs في containers)
- NVIDIA Driver + pynvml (اختياري، لدعم GPU)
- PySide6 (لتطبيق سطح المكتب)

## ملاحظات مهمة | Important Notes

1. **الأمان**: هذا النظام يشغل أوامر على أجهزة أخرى. استخدمه فقط على أجهزة تملكها أو لديك إذن صريح باستخدامها.

2. **الشبكة**: يجب أن تكون الأجهزة قادرة على التواصل (نفس الشبكة أو VPN).

3. **Docker**: يُنصح باستخدام Docker لعزل المهام وضمان الأمان.

4. **Windows**: يعمل النظام بالكامل على Windows مع دعم:
   - Process management (taskkill)
   - Disk monitoring (C:\)
   - Machine fingerprint (Registry)
   - Desktop app (.exe)

## التوثيق الإضافي | Additional Documentation

- [API Reference](docs/API_REFERENCE.md)
- [AI Integration Guide](docs/AI_GUIDE.md)
- [Mesh Network Guide](docs/MESH_NETWORK_GUIDE.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## أدوات مشابهة | Similar Tools

- [Ray](https://ray.io) - Distributed computing framework
- [Dask](https://dask.org) - Parallel computing library
- [Kubernetes](https://kubernetes.io) - Container orchestration
- [Slurm](https://slurm.schedmd.com) - HPC workload manager

## الترخيص | License

MIT License
