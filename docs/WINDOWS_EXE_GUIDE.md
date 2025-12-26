# دليل تحويل NebulaCompute إلى ملف EXE على Windows
# Windows EXE Build Guide

---

## المتطلبات الأساسية | Prerequisites

قبل البدء، تأكد من تثبيت:

| المتطلب | الإصدار | ملاحظات |
|---------|---------|---------|
| Python | 3.10+ | [تحميل](https://www.python.org/downloads/) |
| Git | أحدث إصدار | [تحميل](https://git-scm.com/download/win) |
| Windows | 10/11 | 64-bit مفضل |

---

## الخطوة 1: استنساخ المشروع

### باستخدام CMD:

```cmd
:: افتح Command Prompt (اضغط Win + R ثم اكتب cmd)

:: انتقل إلى المجلد المطلوب (مثلاً سطح المكتب)
cd %USERPROFILE%\Desktop

:: استنسخ المشروع
git clone https://github.com/salahuddin1992/theEnd.git

:: ادخل إلى مجلد المشروع
cd theEnd
```

### باستخدام PowerShell:

```powershell
# افتح PowerShell (اضغط Win + X ثم اختر Windows PowerShell)

# انتقل إلى سطح المكتب
Set-Location $env:USERPROFILE\Desktop

# استنسخ المشروع
git clone https://github.com/salahuddin1992/theEnd.git

# ادخل إلى مجلد المشروع
Set-Location theEnd
```

---

## الخطوة 2: إنشاء بيئة افتراضية

### باستخدام CMD:

```cmd
:: إنشاء البيئة الافتراضية
python -m venv venv

:: تفعيل البيئة
venv\Scripts\activate.bat

:: التأكد من التفعيل (ستظهر (venv) في بداية السطر)
echo %VIRTUAL_ENV%
```

### باستخدام PowerShell:

```powershell
# إنشاء البيئة الافتراضية
python -m venv venv

# إذا واجهت خطأ في السياسة، شغّل هذا الأمر أولاً (كمسؤول):
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# تفعيل البيئة
.\venv\Scripts\Activate.ps1

# التأكد من التفعيل
$env:VIRTUAL_ENV
```

---

## الخطوة 3: تثبيت المتطلبات

### الأمر الموحد (CMD و PowerShell):

```cmd
:: تثبيت المشروع مع متطلبات سطح المكتب والبناء
pip install -e ".[desktop,build]"

:: أو تثبيت كل شيء
pip install -e ".[all]"
```

**المتطلبات التي سيتم تثبيتها:**
- `PySide6` - إطار Qt6 للواجهة الرسومية
- `qasync` - دعم asyncio مع Qt
- `PyInstaller` - لبناء ملف exe
- `httpx` - عميل HTTP غير متزامن
- `websockets` - دعم WebSocket

---

## الخطوة 4: بناء ملف EXE

### الأمر الموحد (CMD و PowerShell):

```cmd
:: الانتقال إلى مجلد سطح المكتب
cd src\distributed_cluster\desktop

:: بناء النسخة الكاملة
python build_exe.py

:: أو بناء نسخة خفيفة (أصغر حجماً)
python build_exe.py --mode minimal

:: تنظيف ملفات البناء السابقة فقط
python build_exe.py --clean
```

**خيارات البناء:**

| الخيار | الوصف |
|--------|-------|
| `--mode full` | النسخة الكاملة (افتراضي) |
| `--mode minimal` | نسخة خفيفة بدون ميزات إضافية |
| `--clean` | تنظيف ملفات البناء |
| `--installer` | إنشاء سكريبت NSIS installer |

---

## الخطوة 5: موقع الملف التنفيذي

بعد نجاح البناء، ستجد الملف في:

```
theEnd\dist\NebulaCompute.exe
```

**معلومات الملف:**
- الحجم المتوقع: 80-150 MB (حسب وضع البناء)
- نوع الملف: Windows Executable (.exe)
- لا يحتاج تثبيت: ملف محمول (portable)

---

## الخطوة 6: تشغيل التطبيق

### الطريقة 1: النقر المزدوج

```
ببساطة اذهب إلى:
theEnd\dist\NebulaCompute.exe
وانقر نقراً مزدوجاً على الملف
```

### الطريقة 2: من سطر الأوامر

```cmd
:: تشغيل مباشر
.\dist\NebulaCompute.exe

:: تشغيل مع الاتصال بخادم
.\dist\NebulaCompute.exe --server http://localhost:8080

:: تشغيل مع token
.\dist\NebulaCompute.exe --server http://localhost:8080 --token YOUR_TOKEN
```

---

## الخطوة 7: استخدام التطبيق

### عند التشغيل لأول مرة:

1. ستظهر نافذة **الاتصال بالخادم** (Connection Dialog)
2. أدخل:
   - **عنوان الخادم**: `http://localhost:8080` (للاختبار المحلي)
   - **Token**: (اختياري) رمز المصادقة
   - **اسم الاتصال**: اسم لتذكر هذا الخادم

### التنقل في التطبيق:

| اختصار | الوظيفة |
|--------|---------|
| `Ctrl+1` | لوحة المعلومات (Dashboard) |
| `Ctrl+2` | المهام (Jobs) |
| `Ctrl+3` | العمّال (Workers) |
| `Ctrl+K` | الاتصال بخادم جديد |
| `Ctrl+N` | إرسال مهمة جديدة |
| `F5` | تحديث البيانات |
| `` Ctrl+` `` | إظهار/إخفاء Terminal |

---

## سكريبت البناء الكامل (نسخ ولصق)

### CMD - الطريقة السريعة:

```cmd
@echo off
echo ===================================
echo  NebulaCompute EXE Builder
echo ===================================

:: الانتقال إلى سطح المكتب
cd /d %USERPROFILE%\Desktop

:: استنساخ المشروع (إذا لم يكن موجوداً)
if not exist "theEnd" (
    echo Cloning repository...
    git clone https://github.com/salahuddin1992/theEnd.git
)

:: الدخول إلى المشروع
cd theEnd

:: إنشاء البيئة الافتراضية
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

:: تفعيل البيئة
call venv\Scripts\activate.bat

:: تثبيت المتطلبات
echo Installing dependencies...
pip install -e ".[desktop,build]" --quiet

:: بناء EXE
echo Building EXE...
cd src\distributed_cluster\desktop
python build_exe.py

echo.
echo ===================================
echo  Build Complete!
echo  File: %USERPROFILE%\Desktop\theEnd\dist\NebulaCompute.exe
echo ===================================
pause
```

### PowerShell - الطريقة السريعة:

```powershell
Write-Host "===================================" -ForegroundColor Cyan
Write-Host " NebulaCompute EXE Builder" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan

# الانتقال إلى سطح المكتب
Set-Location $env:USERPROFILE\Desktop

# استنساخ المشروع (إذا لم يكن موجوداً)
if (-not (Test-Path "theEnd")) {
    Write-Host "Cloning repository..." -ForegroundColor Yellow
    git clone https://github.com/salahuddin1992/theEnd.git
}

# الدخول إلى المشروع
Set-Location theEnd

# إنشاء البيئة الافتراضية
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# تفعيل البيئة
& .\venv\Scripts\Activate.ps1

# تثبيت المتطلبات
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -e ".[desktop,build]" --quiet

# بناء EXE
Write-Host "Building EXE..." -ForegroundColor Yellow
Set-Location src\distributed_cluster\desktop
python build_exe.py

Write-Host ""
Write-Host "===================================" -ForegroundColor Green
Write-Host " Build Complete!" -ForegroundColor Green
Write-Host " File: $env:USERPROFILE\Desktop\theEnd\dist\NebulaCompute.exe" -ForegroundColor White
Write-Host "===================================" -ForegroundColor Green
```

---

## حل المشاكل الشائعة

### مشكلة 1: `python: command not found`

**الحل:**
```cmd
:: تأكد من تثبيت Python وإضافته إلى PATH
:: أثناء التثبيت، اختر "Add Python to PATH"

:: أو استخدم المسار الكامل
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe -m venv venv
```

### مشكلة 2: خطأ في ExecutionPolicy (PowerShell)

**الحل:**
```powershell
# شغّل PowerShell كمسؤول (Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### مشكلة 3: `ModuleNotFoundError: No module named 'PySide6'`

**الحل:**
```cmd
pip install PySide6 qasync
```

### مشكلة 4: PyInstaller خطأ في البناء

**الحل:**
```cmd
:: تحديث PyInstaller
pip install --upgrade pyinstaller

:: تنظيف ثم إعادة البناء
python build_exe.py --clean
python build_exe.py
```

### مشكلة 5: ملف EXE لا يعمل

**الحل:**
```cmd
:: شغّل من CMD لرؤية الأخطاء
cd dist
NebulaCompute.exe

:: أو تحقق من Windows Event Viewer
```

---

## إنشاء Installer (اختياري)

لإنشاء ملف تثبيت Windows (NSIS):

### الخطوة 1: تثبيت NSIS

```
حمّل من: https://nsis.sourceforge.io/Download
```

### الخطوة 2: إنشاء سكريبت Installer

```cmd
python build_exe.py --installer
```

### الخطوة 3: بناء Installer

```cmd
:: شغّل NSIS على الملف المولّد
makensis installer.nsi
```

---

## البنية النهائية للملفات

```
theEnd/
├── dist/
│   └── NebulaCompute.exe    ← الملف التنفيذي (80-150 MB)
├── build/                    ← ملفات البناء المؤقتة
├── NebulaCompute.spec        ← ملف إعدادات PyInstaller
└── installer.nsi             ← سكريبت NSIS (إذا طلبته)
```

---

## ملخص الأوامر الأساسية

| المهمة | الأمر (CMD) | الأمر (PowerShell) |
|--------|-------------|---------------------|
| استنساخ | `git clone <url>` | `git clone <url>` |
| إنشاء venv | `python -m venv venv` | `python -m venv venv` |
| تفعيل venv | `venv\Scripts\activate.bat` | `.\venv\Scripts\Activate.ps1` |
| تثبيت | `pip install -e ".[desktop,build]"` | `pip install -e ".[desktop,build]"` |
| بناء EXE | `python build_exe.py` | `python build_exe.py` |
| تشغيل | `.\dist\NebulaCompute.exe` | `.\dist\NebulaCompute.exe` |

---

## روابط مفيدة

- [تحميل Python](https://www.python.org/downloads/)
- [تحميل Git](https://git-scm.com/download/win)
- [وثائق PySide6](https://doc.qt.io/qtforpython/)
- [وثائق PyInstaller](https://pyinstaller.org/en/stable/)
- [تحميل NSIS](https://nsis.sourceforge.io/Download)

---

## الدعم

إذا واجهت أي مشاكل:
1. افتح issue على GitHub: https://github.com/salahuddin1992/theEnd/issues
2. تحقق من قسم حل المشاكل أعلاه
3. تأكد من تثبيت جميع المتطلبات بشكل صحيح
