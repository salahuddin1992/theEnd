@echo off
:: NebulaCompute Build Script for Windows
:: سكربت بناء NebulaCompute لنظام ويندوز
::
:: Usage:
::   build.bat              - Default build
::   build.bat fast         - Quick build
::   build.bat optimized    - Optimized build
::   build.bat debug        - Debug build with console
::   build.bat clean        - Clean build artifacts
::   build.bat install      - Install dependencies
::   build.bat help         - Show help

setlocal EnableDelayedExpansion

:: Colors
set "GREEN=[92m"
set "YELLOW=[93m"
set "RED=[91m"
set "CYAN=[96m"
set "RESET=[0m"

:: Header
echo.
echo %CYAN%======================================================%RESET%
echo %CYAN%         NebulaCompute PyInstaller Builder            %RESET%
echo %CYAN%======================================================%RESET%
echo.

:: Parse arguments
set "MODE=default"
set "ACTION=build"

if "%1"=="" goto :run
if /i "%1"=="fast" set "MODE=fast" & goto :run
if /i "%1"=="optimized" set "MODE=optimized" & goto :run
if /i "%1"=="debug" set "MODE=debug" & goto :run
if /i "%1"=="clean" set "ACTION=clean" & goto :run
if /i "%1"=="install" set "ACTION=install" & goto :run
if /i "%1"=="info" set "ACTION=info" & goto :run
if /i "%1"=="help" goto :help
if /i "%1"=="-h" goto :help
if /i "%1"=="--help" goto :help

:: Unknown argument, pass it through
set "EXTRA_ARGS=%*"
goto :run_with_args

:run
if "%ACTION%"=="clean" (
    echo %YELLOW%Cleaning build artifacts...%RESET%
    python build.py --clean
    goto :end
)

if "%ACTION%"=="install" (
    echo %YELLOW%Installing dependencies...%RESET%
    python build.py --install-deps
    goto :end
)

if "%ACTION%"=="info" (
    python build.py --info
    goto :end
)

:: Run build with mode
echo %GREEN%Building with mode: %MODE%%RESET%
python build.py --mode %MODE%
goto :end

:run_with_args
echo %GREEN%Running with custom arguments...%RESET%
python build.py %EXTRA_ARGS%
goto :end

:help
echo.
echo Usage: build.bat [command] [options]
echo.
echo Commands:
echo   (none)      Build with default settings
echo   fast        Quick build with minimal optimization
echo   optimized   Build with maximum optimization
echo   debug       Debug build with console window
echo   clean       Clean build artifacts
echo   install     Install build dependencies
echo   info        Show build configuration info
echo   help        Show this help message
echo.
echo Advanced options (pass directly to build.py):
echo   --onedir    Create one-directory bundle
echo   --console   Enable console window
echo   --no-upx    Disable UPX compression
echo   --version X Override version string
echo   --name X    Override output name
echo.
echo Examples:
echo   build.bat                     Default build
echo   build.bat fast                Quick build
echo   build.bat --onedir --console  Custom options
echo.
goto :end

:end
echo.
if %ERRORLEVEL% EQU 0 (
    echo %GREEN%Done!%RESET%
) else (
    echo %RED%Build failed with error code: %ERRORLEVEL%%RESET%
)
endlocal
