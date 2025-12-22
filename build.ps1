# NebulaCompute Build Script for Windows
# Run: powershell -ExecutionPolicy Bypass -File build.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  NebulaCompute EXE Builder" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan

# Install dependencies
Write-Host "`n[1/3] Installing dependencies..." -ForegroundColor Yellow
pip install pyinstaller PySide6 qasync httpx websockets aiofiles aiosqlite pydantic fastapi uvicorn --quiet

# Find the main.py file
$mainFile = $null
$possiblePaths = @(
    "src\distributed_cluster\desktop\main.py",
    "src\distributed_cluster\desktop\app_entry.py",
    "distributed_cluster\desktop\main.py",
    "desktop\main.py",
    "main.py"
)

foreach ($path in $possiblePaths) {
    if (Test-Path $path) {
        $mainFile = $path
        Write-Host "[2/3] Found: $path" -ForegroundColor Green
        break
    }
}

if (-not $mainFile) {
    Write-Host "`nERROR: Cannot find main.py file!" -ForegroundColor Red
    Write-Host "`nFiles in current directory:" -ForegroundColor Yellow
    Get-ChildItem -Recurse -Filter "*.py" | Select-Object -First 20 | ForEach-Object { Write-Host $_.FullName }
    exit 1
}

# Build EXE
Write-Host "`n[3/3] Building EXE..." -ForegroundColor Yellow

$srcPath = "src"
if (-not (Test-Path $srcPath)) {
    $srcPath = "."
}

pyinstaller --name=NebulaCompute --windowed --onefile --paths=$srcPath $mainFile --noconfirm

# Check result
if (Test-Path "dist\NebulaCompute.exe") {
    Write-Host "`n======================================" -ForegroundColor Green
    Write-Host "  BUILD SUCCESSFUL!" -ForegroundColor Green
    Write-Host "======================================" -ForegroundColor Green
    Write-Host "`nEXE Location: $((Get-Item 'dist\NebulaCompute.exe').FullName)" -ForegroundColor Cyan
    $size = [math]::Round((Get-Item "dist\NebulaCompute.exe").Length / 1MB, 2)
    Write-Host "Size: $size MB" -ForegroundColor Cyan
} else {
    Write-Host "`nBUILD FAILED!" -ForegroundColor Red
}
