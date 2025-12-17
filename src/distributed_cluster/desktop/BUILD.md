# Building NebulaCompute Desktop
# بناء تطبيق سطح المكتب

## Requirements / المتطلبات

### For Running (التشغيل):
```bash
pip install distributed-cluster[desktop]
```

### For Building EXE (بناء ملف التنفيذ):
```bash
pip install distributed-cluster[desktop,build]
```

## Running from Source / التشغيل من الكود

```bash
# Run directly
python -m distributed_cluster.desktop.main

# Or using entry point
dc-desktop
```

## Building Windows EXE / بناء ملف Windows

### Method 1: Using build script (الطريقة الأولى)
```bash
cd src/distributed_cluster/desktop
python build_exe.py
```

The executable will be created at: `dist/NebulaCompute.exe`

### Method 2: Manual PyInstaller (الطريقة اليدوية)
```bash
pyinstaller --name=NebulaCompute \
    --windowed \
    --onefile \
    --hidden-import=PySide6.QtCore \
    --hidden-import=PySide6.QtGui \
    --hidden-import=PySide6.QtWidgets \
    --hidden-import=qasync \
    src/distributed_cluster/desktop/main.py
```

## Creating Installer / إنشاء برنامج التثبيت

After building the EXE, you can create a Windows installer using NSIS:

1. Generate NSIS script:
```bash
python build_exe.py --installer
```

2. Install NSIS from https://nsis.sourceforge.io/

3. Compile the installer:
```bash
makensis installer.nsi
```

## Build Options / خيارات البناء

| Option | Description |
|--------|-------------|
| `--clean` | Clean build artifacts |
| `--installer` | Create NSIS installer script |

## Troubleshooting / حل المشاكل

### Missing DLLs
If you get DLL errors on Windows:
```bash
pip install --upgrade PySide6
```

### Large File Size
To reduce EXE size:
1. Use UPX compression (add `--upx-dir=<path>` to PyInstaller)
2. Exclude unused modules

### Icon Not Showing
Generate the icon first:
```bash
cd src/distributed_cluster/desktop/resources
python icon.py
```

## System Requirements / متطلبات النظام

- Windows 10/11 (64-bit)
- 4GB RAM minimum
- 500MB disk space

## Features / الميزات

- Real-time cluster monitoring
- Job submission and management
- Worker monitoring
- System tray integration
- Embedded terminal
- Dark/Light themes
