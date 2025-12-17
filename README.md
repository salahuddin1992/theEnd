# NebulaCompute - نظام الحوسبة الموزّعة

<div align="center">

**نظام حوسبة موزّعة لتوزيع المهام على عدة أجهزة وإدارتها من نقطة تحكم مركزية**

[English](#english) | [العربية](#arabic)

</div>

---

<a name="arabic"></a>

## المفهوم الأساسي

```
                    ┌─────────────────────┐
                    │     Master Node     │
                    │  (Control Plane)    │
                    ├─────────────────────┤
                    │  • REST API         │
                    │  • Scheduler        │
                    │  • State Store      │
                    │  • Health Monitor   │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼────────┐ ┌─────▼─────┐ ┌───────▼───────┐
     │   Worker #1     │ │ Worker #2 │ │   Worker #N   │
     │ CPU: 8, GPU: 1  │ │ CPU: 16   │ │ CPU: 4, GPU:2 │
     └─────────────────┘ └───────────┘ └───────────────┘
```

## الميزات

- **توزيع المهام**: إرسال مهام للعمّال وتنفيذها على مواردهم
- **جدولة ذكية**: Bin-packing scheduler يوزع المهام بناءً على الموارد المتاحة (CPU/RAM/GPU)
- **عزل آمن**: تنفيذ المهام داخل Docker containers
- **مراقبة حية**: WebSocket للتحديثات الفورية
- **تحمّل الأخطاء**: إعادة المحاولة التلقائية عند الفشل
- **دعم GPU**: تخصيص GPUs للمهام التي تحتاجها
- **واجهة سطح المكتب**: تطبيق Desktop للتحكم البصري
- **دعم AI**: تشغيل نماذج الذكاء الاصطناعي الموزعة

## متطلبات النظام

| المتطلب | الإصدار المطلوب |
|---------|-----------------|
| Python | 3.10 أو أحدث |
| pip | 23.0 أو أحدث |
| Docker | اختياري (لتشغيل jobs في containers) |
| NVIDIA Driver | اختياري (لدعم GPU) |

---

# دليل التثبيت والتشغيل

## الطريقة 1: التثبيت المحلي (بدون Docker)

### الخطوة 1: استنساخ المشروع

<details>
<summary><b>Windows CMD</b></summary>

```cmd
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
git clone https://github.com/salahuddin1992/theEnd.git
Set-Location theEnd
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd
```
</details>

---

### الخطوة 2: إنشاء بيئة افتراضية

<details>
<summary><b>Windows CMD</b></summary>

```cmd
:: إنشاء البيئة الافتراضية
python -m venv venv

:: تفعيل البيئة
venv\Scripts\activate.bat

:: للتحقق من التفعيل (يجب أن ترى (venv) في بداية السطر)
where python
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
# إنشاء البيئة الافتراضية
python -m venv venv

# تفعيل البيئة
.\venv\Scripts\Activate.ps1

# إذا واجهت خطأ في السياسة، شغّل هذا الأمر أولاً:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# للتحقق من التفعيل
Get-Command python
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
# إنشاء البيئة الافتراضية
python3 -m venv venv

# تفعيل البيئة
source venv/bin/activate

# للتحقق من التفعيل
which python
```
</details>

---

### الخطوة 3: تثبيت المشروع

<details>
<summary><b>Windows CMD</b></summary>

```cmd
:: تثبيت المشروع مع جميع المتطلبات
pip install -e ".[dev]"

:: أو تثبيت مع جميع الإضافات
pip install -e ".[all]"
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
# تثبيت المشروع مع جميع المتطلبات
pip install -e ".[dev]"

# أو تثبيت مع جميع الإضافات
pip install -e ".[all]"
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
# تثبيت المشروع مع جميع المتطلبات
pip install -e ".[dev]"

# أو تثبيت مع جميع الإضافات
pip install -e ".[all]"
```
</details>

---

### الخطوة 4: تشغيل Master (الخادم الرئيسي)

**افتح نافذة طرفية جديدة:**

<details>
<summary><b>Windows CMD</b></summary>

```cmd
:: تفعيل البيئة
cd theEnd
venv\Scripts\activate.bat

:: تشغيل Master على المنفذ 8080
dc-master start --host 0.0.0.0 --port 8080

:: أو مع ملف إعدادات
dc-master start --config config.example.yaml
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
# تفعيل البيئة
Set-Location theEnd
.\venv\Scripts\Activate.ps1

# تشغيل Master على المنفذ 8080
dc-master start --host 0.0.0.0 --port 8080

# أو مع ملف إعدادات
dc-master start --config config.example.yaml
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
# تفعيل البيئة
cd theEnd
source venv/bin/activate

# تشغيل Master على المنفذ 8080
dc-master start --host 0.0.0.0 --port 8080

# أو مع ملف إعدادات
dc-master start --config config.example.yaml
```
</details>

**بعد التشغيل، ستظهر رسالة:**
```
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

---

### الخطوة 5: تشغيل Worker (على كل جهاز عامل)

**افتح نافذة طرفية جديدة (أبقِ Master يعمل):**

<details>
<summary><b>Windows CMD</b></summary>

```cmd
:: تفعيل البيئة
cd theEnd
venv\Scripts\activate.bat

:: تشغيل Worker والاتصال بـ Master
dc-worker start --master-url http://localhost:8080

:: أو مع tags للتصنيف
dc-worker start --master-url http://localhost:8080 --tags gpu,high-memory

:: لعرض معلومات الجهاز
dc-worker info
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
# تفعيل البيئة
Set-Location theEnd
.\venv\Scripts\Activate.ps1

# تشغيل Worker والاتصال بـ Master
dc-worker start --master-url http://localhost:8080

# أو مع tags للتصنيف
dc-worker start --master-url http://localhost:8080 --tags gpu,high-memory

# لعرض معلومات الجهاز
dc-worker info
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
# تفعيل البيئة
cd theEnd
source venv/bin/activate

# تشغيل Worker والاتصال بـ Master
dc-worker start --master-url http://localhost:8080

# أو مع tags للتصنيف
dc-worker start --master-url http://localhost:8080 --tags gpu,high-memory

# لعرض معلومات الجهاز
dc-worker info
```
</details>

**ملاحظة:** إذا كان Worker على جهاز مختلف، استبدل `localhost` بعنوان IP الـ Master:
```
dc-worker start --master-url http://192.168.1.100:8080
```

---

### الخطوة 6: إرسال المهام (Jobs)

**افتح نافذة طرفية جديدة:**

<details>
<summary><b>Windows CMD</b></summary>

```cmd
:: تفعيل البيئة
cd theEnd
venv\Scripts\activate.bat

:: إرسال مهمة بسيطة
dc-submit run "echo Hello World"

:: إرسال مهمة Python
dc-submit run "python -c \"print('Hello from NebulaCompute!')\""

:: إرسال مهمة مع متطلبات موارد
dc-submit run "python train.py" --cpu 4 --memory 8192 --gpu 1

:: إرسال مهمة داخل Docker
dc-submit run "python script.py" --docker python:3.11

:: انتظار النتيجة
dc-submit run "python test.py" --wait

:: إرسال مجموعة مهام من ملف
dc-submit batch examples/jobs.example.json
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
# تفعيل البيئة
Set-Location theEnd
.\venv\Scripts\Activate.ps1

# إرسال مهمة بسيطة
dc-submit run "echo Hello World"

# إرسال مهمة Python
dc-submit run "python -c `"print('Hello from NebulaCompute!')`""

# إرسال مهمة مع متطلبات موارد
dc-submit run "python train.py" --cpu 4 --memory 8192 --gpu 1

# إرسال مهمة داخل Docker
dc-submit run "python script.py" --docker python:3.11

# انتظار النتيجة
dc-submit run "python test.py" --wait

# إرسال مجموعة مهام من ملف
dc-submit batch examples/jobs.example.json
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
# تفعيل البيئة
cd theEnd
source venv/bin/activate

# إرسال مهمة بسيطة
dc-submit run "echo Hello World"

# إرسال مهمة Python
dc-submit run "python -c \"print('Hello from NebulaCompute!')\""

# إرسال مهمة مع متطلبات موارد
dc-submit run "python train.py" --cpu 4 --memory 8192 --gpu 1

# إرسال مهمة داخل Docker
dc-submit run "python script.py" --docker python:3.11

# انتظار النتيجة
dc-submit run "python test.py" --wait

# إرسال مجموعة مهام من ملف
dc-submit batch examples/jobs.example.json
```
</details>

---

### الخطوة 7: المراقبة والإدارة

<details>
<summary><b>جميع الأنظمة</b></summary>

```bash
# حالة الكلاستر
dc-master status

# قائمة Workers المتصلين
dc-master workers

# قائمة المهام
dc-master jobs
dc-submit list --status running

# تفاصيل مهمة معينة
dc-submit status <job-id>

# إلغاء مهمة
dc-submit cancel <job-id>
```
</details>

---

## الطريقة 2: التشغيل باستخدام Docker Compose

### التشغيل السريع

<details>
<summary><b>Windows CMD</b></summary>

```cmd
cd theEnd

:: تشغيل الكلاستر (master + 2 workers)
docker-compose up -d

:: عرض الحالة
docker-compose ps

:: عرض السجلات
docker-compose logs -f

:: إيقاف الكلاستر
docker-compose down
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
Set-Location theEnd

# تشغيل الكلاستر (master + 2 workers)
docker-compose up -d

# عرض الحالة
docker-compose ps

# عرض السجلات
docker-compose logs -f

# إيقاف الكلاستر
docker-compose down
```
</details>

<details>
<summary><b>Linux / macOS Terminal</b></summary>

```bash
cd theEnd

# تشغيل الكلاستر (master + 2 workers)
docker-compose up -d

# عرض الحالة
docker-compose ps

# عرض السجلات
docker-compose logs -f

# إيقاف الكلاستر
docker-compose down
```
</details>

### مع MinIO (تخزين S3)

```bash
docker-compose --profile storage up -d
```

### مع Redis (للتوفر العالي)

```bash
docker-compose --profile ha up -d
```

---

## الطريقة 3: التشغيل باستخدام Conda

<details>
<summary><b>جميع الأنظمة</b></summary>

```bash
# إنشاء البيئة من ملف environment.yml
conda env create -f environment.yml

# تفعيل البيئة
conda activate theend-env

# تثبيت المشروع
pip install -e .

# تشغيل Master
dc-master start --port 8080
```
</details>

---

## الأوامر المتاحة (CLI)

| الأمر | الوصف |
|-------|-------|
| `dc-master` | إدارة Master node |
| `dc-worker` | إدارة Worker node |
| `dc-submit` | إرسال وإدارة المهام |
| `dc-mesh` | إدارة شبكة Mesh |
| `dc-web` | تشغيل واجهة الويب |
| `dc-notify` | إدارة الإشعارات |
| `dc-desktop` | تشغيل تطبيق سطح المكتب |
| `dc-ai` | أدوات الذكاء الاصطناعي |
| `dc-inference` | تشغيل خادم الاستدلال |

### أمثلة الأوامر

```bash
# عرض المساعدة لأي أمر
dc-master --help
dc-worker --help
dc-submit --help

# عرض معلومات النظام
dc-worker info

# فحص صحة الكلاستر
dc-master health
```

---

## API Reference

Master يوفر REST API على المنفذ المحدد:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | فحص الصحة |
| GET | `/stats` | إحصائيات الكلاستر |
| POST | `/workers/register` | تسجيل worker جديد |
| POST | `/workers/heartbeat` | Heartbeat من worker |
| GET | `/workers` | قائمة workers |
| POST | `/jobs` | إرسال مهمة جديدة |
| GET | `/jobs` | قائمة المهام |
| GET | `/jobs/{id}` | تفاصيل مهمة |
| DELETE | `/jobs/{id}` | إلغاء مهمة |
| GET | `/events` | الأحداث الأخيرة |
| WS | `/ws` | WebSocket للتحديثات الحية |

### مثال استخدام API بـ Python

```python
import httpx

# إرسال مهمة
response = httpx.post("http://localhost:8080/jobs", json={
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
job = httpx.get(f"http://localhost:8080/jobs/{job_id}").json()
print(job["status"], job.get("result"))
```

---

## بنية المشروع

```
theEnd/
├── src/
│   └── distributed_cluster/
│       ├── ai/                  # أدوات الذكاء الاصطناعي
│       ├── cli/                 # أدوات سطر الأوامر
│       │   ├── master_cli.py    # dc-master
│       │   ├── worker_cli.py    # dc-worker
│       │   ├── submit_cli.py    # dc-submit
│       │   └── ...
│       ├── core/                # إعدادات وأدوات أساسية
│       ├── desktop/             # تطبيق سطح المكتب
│       ├── grpc/                # دعم gRPC
│       ├── master/              # خادم Master
│       ├── mesh/                # شبكة Mesh
│       ├── models/              # نماذج البيانات
│       ├── notifications/       # نظام الإشعارات
│       ├── observability/       # المراقبة والتتبع
│       ├── plugins/             # نظام الإضافات
│       ├── scheduler/           # جدولة المهام
│       ├── security/            # الأمان
│       ├── storage/             # التخزين
│       ├── web/                 # واجهة الويب
│       ├── worker/              # خادم Worker
│       └── workflow/            # إدارة سير العمل
├── config/                      # ملفات الإعدادات
├── deploy/                      # ملفات النشر
├── docs/                        # التوثيق
├── examples/                    # أمثلة
├── tests/                       # الاختبارات
├── docker-compose.yml           # تكوين Docker
├── pyproject.toml               # إعدادات المشروع
└── README.md                    # هذا الملف
```

---

## سياسات الجدولة

| السياسة | الوصف |
|---------|-------|
| `first_fit` | أول worker مناسب |
| `best_fit` | أقل موارد فائضة (bin packing) - الافتراضي |
| `worst_fit` | أكثر موارد فائضة (spread) |
| `round_robin` | بالتناوب |
| `least_loaded` | أقل عدد jobs نشطة |

---

## حل المشاكل الشائعة

### خطأ: `dc-master: command not found`

```bash
# تأكد من تفعيل البيئة الافتراضية
# Windows CMD:
venv\Scripts\activate.bat

# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Linux/macOS:
source venv/bin/activate
```

### خطأ: `ModuleNotFoundError`

```bash
# أعد تثبيت المشروع
pip install -e ".[dev]"
```

### خطأ: PowerShell Execution Policy

```powershell
# شغّل PowerShell كمسؤول ثم:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Worker لا يتصل بـ Master

1. تأكد أن Master يعمل
2. تأكد من صحة عنوان IP
3. تأكد أن المنفذ مفتوح في جدار الحماية

```bash
# فحص الاتصال
curl http://localhost:8080/health
```

---

## ملاحظات مهمة

1. **الأمان**: هذا النظام يشغل أوامر على أجهزة أخرى. استخدمه فقط على أجهزة تملكها أو لديك إذن صريح باستخدامها.

2. **الشبكة**: يجب أن تكون الأجهزة قادرة على التواصل (نفس الشبكة أو VPN).

3. **Docker**: يُنصح باستخدام Docker لعزل المهام وضمان الأمان.

---

<a name="english"></a>

# English

## Quick Start

```bash
# Clone
git clone https://github.com/salahuddin1992/theEnd.git
cd theEnd

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install
pip install -e ".[dev]"

# Start Master (Terminal 1)
dc-master start --port 8080

# Start Worker (Terminal 2)
dc-worker start --master-url http://localhost:8080

# Submit Job (Terminal 3)
dc-submit run "echo Hello World"
```

## Docker Quick Start

```bash
docker-compose up -d
```

---

## License

MIT License

---

## Similar Tools

- [Ray](https://ray.io) - Distributed computing framework
- [Dask](https://dask.org) - Parallel computing library
- [Kubernetes](https://kubernetes.io) - Container orchestration
- [Slurm](https://slurm.schedmd.com) - HPC workload manager
