<#
.SYNOPSIS
    NebulaCompute Build Script for Windows
    سكريبت البناء لنظام ويندوز

.DESCRIPTION
    Complete PyInstaller build system for NebulaCompute Desktop application.
    Supports multiple build modes, installer creation, and code signing.

.PARAMETER Mode
    Build mode: debug, release (default), minimal, full

.PARAMETER Version
    Override version number

.PARAMETER Installer
    Create installer after build (nsis, inno, msi)

.PARAMETER Console
    Show console window

.PARAMETER OneDir
    Create directory instead of single file

.PARAMETER Clean
    Clean build artifacts only

.EXAMPLE
    .\build.ps1
    Default release build

.EXAMPLE
    .\build.ps1 -Mode debug
    Debug build with console

.EXAMPLE
    .\build.ps1 -Mode minimal
    Minimal build (smaller size)

.EXAMPLE
    .\build.ps1 -Installer nsis
    Build with NSIS installer

.EXAMPLE
    .\build.ps1 -Clean
    Clean build artifacts only

.NOTES
    Author: NebulaCompute Team
    Requires: Python 3.10+, PyInstaller
#>

[CmdletBinding()]
param(
    [ValidateSet("debug", "release", "minimal", "full")]
    [string]$Mode = "release",

    [string]$Version = "",

    [ValidateSet("", "none", "nsis", "inno", "msi")]
    [string]$Installer = "",

    [switch]$Console,

    [switch]$OneDir,

    [switch]$Clean,

    [switch]$Help
)

# ══════════════════════════════════════════════════════════════════
# Configuration / الإعدادات
# ══════════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
$APP_NAME = "NebulaCompute"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = $SCRIPT_DIR
$SRC_PATH = Join-Path $PROJECT_ROOT "src"
$DESKTOP_PATH = Join-Path $SRC_PATH "distributed_cluster\desktop"
$WEB_PATH = Join-Path $SRC_PATH "distributed_cluster\web"
$DIST_PATH = Join-Path $PROJECT_ROOT "dist"
$BUILD_PATH = Join-Path $PROJECT_ROOT "build"

# ══════════════════════════════════════════════════════════════════
# Functions / الدوال
# ══════════════════════════════════════════════════════════════════

function Write-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║                                                                    ║" -ForegroundColor Cyan
    Write-Host "║   ███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗              ║" -ForegroundColor White
    Write-Host "║   ████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗             ║" -ForegroundColor White
    Write-Host "║   ██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║             ║" -ForegroundColor White
    Write-Host "║   ██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║             ║" -ForegroundColor White
    Write-Host "║   ██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║             ║" -ForegroundColor White
    Write-Host "║   ╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝             ║" -ForegroundColor White
    Write-Host "║                                                                    ║" -ForegroundColor Cyan
    Write-Host "║   PyInstaller Build Script v2.0                                   ║" -ForegroundColor Yellow
    Write-Host "║   نظام البناء المتكامل لويندوز                                     ║" -ForegroundColor Green
    Write-Host "║                                                                    ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("═" * 60) -ForegroundColor Blue
    Write-Host "  $Title" -ForegroundColor Blue
    Write-Host ("═" * 60) -ForegroundColor Blue
    Write-Host ""
}

function Write-LogInfo {
    param([string]$Message)
    Write-Host "ℹ️  $Message" -ForegroundColor Cyan
}

function Write-LogSuccess {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-LogWarning {
    param([string]$Message)
    Write-Host "⚠️  $Message" -ForegroundColor Yellow
}

function Write-LogError {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
}

function Get-ProjectVersion {
    if ($Version -ne "") {
        return $Version
    }

    # Try git
    try {
        $gitVersion = git describe --tags --always 2>$null
        if ($gitVersion) {
            return $gitVersion.TrimStart("v")
        }
    } catch {}

    # Try pyproject.toml
    $pyprojectPath = Join-Path $PROJECT_ROOT "pyproject.toml"
    if (Test-Path $pyprojectPath) {
        $content = Get-Content $pyprojectPath -Raw
        if ($content -match 'version\s*=\s*"([^"]+)"') {
            return $matches[1]
        }
    }

    return "1.0.0"
}

function Test-Python {
    Write-Section "Checking Python / فحص بايثون"

    # Find Python
    $pythonCmd = $null
    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $result = & $cmd --version 2>$null
            if ($result) {
                $pythonCmd = $cmd
                break
            }
        } catch {}
    }

    if (-not $pythonCmd) {
        Write-LogError "Python not found! Please install Python 3.10+"
        exit 1
    }

    $script:PYTHON = $pythonCmd

    # Check version
    $pyVersion = & $PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    Write-LogSuccess "Python: $pyVersion"

    # Validate version
    $major = & $PYTHON -c "import sys; print(sys.version_info.major)"
    $minor = & $PYTHON -c "import sys; print(sys.version_info.minor)"

    if ([int]$major -lt 3 -or ([int]$major -eq 3 -and [int]$minor -lt 10)) {
        Write-LogError "Python 3.10+ required, found $pyVersion"
        exit 1
    }
}

function Install-Dependencies {
    Write-Section "Installing Dependencies / تثبيت التبعيات"

    # Check/install PyInstaller
    try {
        $null = & $PYTHON -c "import PyInstaller" 2>$null
        $pyinstallerVersion = & $PYTHON -m PyInstaller --version 2>$null
        Write-LogSuccess "PyInstaller: $pyinstallerVersion"
    } catch {
        Write-LogWarning "PyInstaller not found, installing..."
        & $PYTHON -m pip install pyinstaller --quiet
        Write-LogSuccess "PyInstaller installed"
    }

    # Check/install PySide6
    try {
        $null = & $PYTHON -c "import PySide6" 2>$null
        Write-LogSuccess "PySide6: installed"
    } catch {
        Write-LogWarning "PySide6 not found, installing..."
        & $PYTHON -m pip install PySide6 --quiet
        Write-LogSuccess "PySide6 installed"
    }

    # Check/install other dependencies
    $deps = @("qasync", "httpx", "websockets", "aiofiles", "aiosqlite", "pydantic")
    foreach ($dep in $deps) {
        try {
            $null = & $PYTHON -c "import $dep" 2>$null
            Write-LogSuccess "${dep}: installed"
        } catch {
            Write-LogWarning "${dep} not found, installing..."
            & $PYTHON -m pip install $dep --quiet
        }
    }

    # Check UPX
    try {
        $upxVersion = upx --version 2>$null | Select-Object -First 1
        if ($upxVersion) {
            Write-LogSuccess "UPX: available"
            $script:UPX_AVAILABLE = $true
        }
    } catch {
        Write-LogInfo "UPX: not installed (optional)"
        $script:UPX_AVAILABLE = $false
    }

    # Platform info
    Write-LogSuccess "Platform: Windows ($env:PROCESSOR_ARCHITECTURE)"
}

function Clear-BuildArtifacts {
    Write-Section "Cleaning Build Artifacts / تنظيف ملفات البناء"

    if (Test-Path $BUILD_PATH) {
        Write-LogInfo "Removing: $BUILD_PATH"
        Remove-Item -Recurse -Force $BUILD_PATH -ErrorAction SilentlyContinue
    }

    if (Test-Path $DIST_PATH) {
        Write-LogInfo "Removing: $DIST_PATH"
        Remove-Item -Recurse -Force $DIST_PATH -ErrorAction SilentlyContinue
    }

    # Remove spec files
    Get-ChildItem -Path $PROJECT_ROOT -Filter "*.spec" | ForEach-Object {
        Write-LogInfo "Removing: $($_.Name)"
        Remove-Item -Force $_.FullName
    }

    # Remove pycache
    Get-ChildItem -Path $PROJECT_ROOT -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
    }

    Write-LogSuccess "Clean complete!"
}

function New-Icon {
    $resourcesPath = Join-Path $DESKTOP_PATH "resources"
    $iconPath = Join-Path $resourcesPath "icon.ico"

    if (-not (Test-Path $resourcesPath)) {
        New-Item -ItemType Directory -Path $resourcesPath -Force | Out-Null
    }

    if (Test-Path $iconPath) {
        return $iconPath
    }

    Write-LogInfo "Creating placeholder icon..."

    # Create minimal ICO using Python
    & $PYTHON -c @"
import os
ico_header = bytes([0x00, 0x00, 0x01, 0x00, 0x01, 0x00])
image_entry = bytes([0x10, 0x10, 0x00, 0x00, 0x01, 0x00, 0x20, 0x00, 0x68, 0x04, 0x00, 0x00, 0x16, 0x00, 0x00, 0x00])
bmp_header = bytes([0x28, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x01, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
pixels = []
for y in range(16):
    for x in range(16):
        b, g, r, a = int((x/15)*200+55), int((y/15)*100+80), 100, 255
        pixels.extend([b, g, r, a])
and_mask = bytes([0x00] * 64)
with open(r'$iconPath', 'wb') as f:
    f.write(ico_header + image_entry + bmp_header + bytes(pixels) + and_mask)
"@

    Write-LogSuccess "Created icon: $iconPath"
    return $iconPath
}

function New-VersionInfo {
    param([string]$AppVersion)

    $versionPath = Join-Path $BUILD_PATH "version_info.txt"

    if (-not (Test-Path $BUILD_PATH)) {
        New-Item -ItemType Directory -Path $BUILD_PATH -Force | Out-Null
    }

    $versionParts = $AppVersion -split '[.-]'
    while ($versionParts.Count -lt 4) { $versionParts += "0" }
    $versionTuple = "($($versionParts[0]), $($versionParts[1]), $($versionParts[2]), $($versionParts[3]))"

    $content = @"
# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=$versionTuple,
        prodvers=$versionTuple,
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable(
                u'040904B0',
                [
                    StringStruct(u'CompanyName', u'NebulaCompute Team'),
                    StringStruct(u'FileDescription', u'NebulaCompute Desktop - Distributed Computing System'),
                    StringStruct(u'FileVersion', u'$AppVersion'),
                    StringStruct(u'InternalName', u'$APP_NAME'),
                    StringStruct(u'LegalCopyright', u'Copyright (c) 2024 NebulaCompute Team'),
                    StringStruct(u'OriginalFilename', u'$APP_NAME.exe'),
                    StringStruct(u'ProductName', u'$APP_NAME'),
                    StringStruct(u'ProductVersion', u'$AppVersion'),
                ]
            )
        ]),
        VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
    ]
)
"@

    Set-Content -Path $versionPath -Value $content -Encoding UTF8
    Write-LogSuccess "Created version info"
    return $versionPath
}

function Build-Executable {
    Write-Section "Building Executable / بناء الملف التنفيذي"

    $appVersion = Get-ProjectVersion

    Write-LogInfo "Name: $APP_NAME"
    Write-LogInfo "Version: $appVersion"
    Write-LogInfo "Mode: $Mode"

    # Find entry point
    $entryPoint = $null
    $possiblePaths = @(
        (Join-Path $DESKTOP_PATH "app_entry.py"),
        (Join-Path $DESKTOP_PATH "main.py")
    )

    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $entryPoint = $path
            break
        }
    }

    if (-not $entryPoint) {
        Write-LogError "Entry point not found!"
        exit 1
    }

    Write-LogInfo "Entry point: $entryPoint"

    # Create resources
    $iconPath = New-Icon
    $versionFile = New-VersionInfo -AppVersion $appVersion

    # Build command
    $args = @(
        "-m", "PyInstaller",
        "--name=$APP_NAME",
        "--clean",
        "--noconfirm"
    )

    # Console/windowed
    if ($Console -or $Mode -eq "debug") {
        $args += "--console"
    } else {
        $args += "--windowed"
    }

    # One file/directory
    if ($OneDir) {
        $args += "--onedir"
    } else {
        $args += "--onefile"
    }

    # Icon
    if (Test-Path $iconPath) {
        $args += "--icon=$iconPath"
    }

    # Version file
    if (Test-Path $versionFile) {
        $args += "--version-file=$versionFile"
    }

    # Runtime hook
    $runtimeHook = Join-Path $DESKTOP_PATH "runtime_hook.py"
    if (Test-Path $runtimeHook) {
        $args += "--runtime-hook=$runtimeHook"
    }

    # Data files
    $dataSep = ";"

    $dataFiles = @(
        @{src = (Join-Path $DESKTOP_PATH "resources"); dest = "distributed_cluster/desktop/resources"},
        @{src = (Join-Path $WEB_PATH "templates"); dest = "distributed_cluster/web/templates"},
        @{src = (Join-Path $WEB_PATH "static"); dest = "distributed_cluster/web/static"},
        @{src = (Join-Path $PROJECT_ROOT "config"); dest = "config"}
    )

    foreach ($data in $dataFiles) {
        if (Test-Path $data.src) {
            $args += "--add-data=$($data.src)$dataSep$($data.dest)"
            Write-LogInfo "  + $($data.dest)"
        }
    }

    # Hidden imports
    $hiddenImports = @(
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "PySide6.QtCharts", "PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtSvgWidgets",
        "qasync", "asyncio",
        "httpx", "httpx._transports", "httpx._transports.default",
        "websockets", "websockets.client", "websockets.legacy", "websockets.legacy.client",
        "distributed_cluster", "distributed_cluster.desktop", "distributed_cluster.desktop.main",
        "distributed_cluster.desktop.main_window", "distributed_cluster.desktop.app_entry",
        "distributed_cluster.desktop.api", "distributed_cluster.desktop.api.client",
        "distributed_cluster.desktop.views", "distributed_cluster.desktop.widgets",
        "distributed_cluster.desktop.ui", "distributed_cluster.desktop.resources",
        "distributed_cluster.models", "distributed_cluster.core",
        "json", "ssl", "certifi", "ctypes", "ctypes.wintypes",
        "jaraco", "jaraco.text", "jaraco.functools", "jaraco.context",
        "pkg_resources", "importlib_metadata", "packaging"
    )

    foreach ($imp in $hiddenImports) {
        $args += "--hidden-import=$imp"
    }

    # Excludes
    $excludes = @(
        "tkinter", "matplotlib", "numpy", "pandas", "scipy",
        "PIL", "IPython", "jupyter", "pytest", "pip", "wheel"
    )

    if ($Mode -eq "minimal") {
        $excludes += @("cryptography", "docker", "pynvml")
    }

    foreach ($exc in $excludes) {
        $args += "--exclude-module=$exc"
    }

    # Collect all
    $args += @(
        "--collect-all=PySide6",
        "--collect-all=httpx",
        "--collect-all=websockets",
        "--collect-all=jaraco"
    )

    # UPX
    if (-not $script:UPX_AVAILABLE) {
        $args += "--noupx"
    }

    # Paths
    $args += @(
        "--distpath=$DIST_PATH",
        "--workpath=$BUILD_PATH",
        "--specpath=$PROJECT_ROOT",
        "--paths=$SRC_PATH"
    )

    # Entry point
    $args += $entryPoint

    Write-LogInfo "Running PyInstaller..."
    Write-Host ""

    # Execute
    & $PYTHON $args

    if ($LASTEXITCODE -ne 0) {
        Write-LogError "Build failed!"
        exit 1
    }

    # Check result
    $exePath = Join-Path $DIST_PATH "$APP_NAME.exe"

    if (Test-Path $exePath) {
        $fileInfo = Get-Item $exePath
        $sizeMB = [math]::Round($fileInfo.Length / 1MB, 2)

        Write-Section "Build Complete! / اكتمل البناء"
        Write-Host ""
        Write-Host "╔══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
        Write-Host "║                     ✅ BUILD SUCCESSFUL!                          ║" -ForegroundColor Green
        Write-Host "╠══════════════════════════════════════════════════════════════════╣" -ForegroundColor Green
        Write-Host "║  📁 Executable: $exePath" -ForegroundColor Green
        Write-Host "║  📊 Size: $sizeMB MB" -ForegroundColor Green
        Write-Host "╚══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green
        Write-Host ""
        Write-LogInfo "To run: $exePath"

        return $exePath
    } else {
        Write-LogError "Executable not found!"
        exit 1
    }
}

function New-NsisInstaller {
    param([string]$ExePath)

    Write-Section "Creating NSIS Installer"

    $appVersion = Get-ProjectVersion
    $iconPath = Join-Path $DESKTOP_PATH "resources\icon.ico"

    $nsisScript = @"
; $APP_NAME Installer
!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "$APP_NAME"
OutFile "${APP_NAME}_Setup_${appVersion}.exe"
InstallDir "`$PROGRAMFILES\$APP_NAME"
RequestExecutionLevel admin

VIProductVersion "${appVersion}.0"
VIAddVersionKey "ProductName" "$APP_NAME"
VIAddVersionKey "FileVersion" "$appVersion"

!define MUI_ABORTWARNING
!define MUI_ICON "$iconPath"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"

Section "Install"
    SetOutPath `$INSTDIR
    File "$ExePath"
    CreateDirectory "`$SMPROGRAMS\$APP_NAME"
    CreateShortCut "`$SMPROGRAMS\$APP_NAME\$APP_NAME.lnk" "`$INSTDIR\$APP_NAME.exe"
    CreateShortCut "`$DESKTOP\$APP_NAME.lnk" "`$INSTDIR\$APP_NAME.exe"
    WriteUninstaller "`$INSTDIR\Uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$APP_NAME" "DisplayName" "$APP_NAME"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$APP_NAME" "UninstallString" "`$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    Delete "`$INSTDIR\$APP_NAME.exe"
    Delete "`$INSTDIR\Uninstall.exe"
    Delete "`$SMPROGRAMS\$APP_NAME\$APP_NAME.lnk"
    Delete "`$DESKTOP\$APP_NAME.lnk"
    RMDir "`$SMPROGRAMS\$APP_NAME"
    RMDir "`$INSTDIR"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\$APP_NAME"
SectionEnd
"@

    $nsisPath = Join-Path $BUILD_PATH "$APP_NAME.nsi"
    Set-Content -Path $nsisPath -Value $nsisScript -Encoding UTF8

    # Try to build
    try {
        $null = Get-Command makensis -ErrorAction Stop
        & makensis $nsisPath
        $installerPath = Join-Path $DIST_PATH "${APP_NAME}_Setup_${appVersion}.exe"
        if (Test-Path $installerPath) {
            Write-LogSuccess "Created installer: $installerPath"
        }
    } catch {
        Write-LogInfo "NSIS not found. Script saved to: $nsisPath"
        Write-LogInfo "Install NSIS and run: makensis $nsisPath"
    }
}

function Show-Help {
    Write-Host @"
Usage: .\build.ps1 [OPTIONS]

Options:
  -Mode <mode>       Build mode: debug, release (default), minimal, full
  -Version <ver>     Override version number
  -Installer <type>  Create installer: nsis, inno, msi
  -Console           Show console window
  -OneDir            Create directory instead of single file
  -Clean             Clean build artifacts only
  -Help              Show this help message

Examples:
  .\build.ps1                          # Default release build
  .\build.ps1 -Mode debug              # Debug build with console
  .\build.ps1 -Mode minimal            # Minimal build (smaller)
  .\build.ps1 -Installer nsis          # Build with NSIS installer
  .\build.ps1 -Clean                   # Clean only

"@
}

# ══════════════════════════════════════════════════════════════════
# Main / الرئيسية
# ══════════════════════════════════════════════════════════════════

if ($Help) {
    Show-Help
    exit 0
}

Write-Banner

if ($Clean) {
    Clear-BuildArtifacts
    exit 0
}

Test-Python
Install-Dependencies
Clear-BuildArtifacts
$exePath = Build-Executable

if ($Installer -and $Installer -ne "none") {
    switch ($Installer) {
        "nsis" { New-NsisInstaller -ExePath $exePath }
        default { Write-LogWarning "Installer type '$Installer' not implemented yet" }
    }
}

Write-LogSuccess "All done! / تم بنجاح!"
