"""
PyInstaller Runtime Hook for NebulaCompute Desktop
خطاف التشغيل لـ PyInstaller

This hook runs before the main application starts.
يعمل هذا الخطاف قبل بدء التطبيق الرئيسي

Features:
- Fix pkg_resources/jaraco import issues
- Setup Qt environment paths
- Configure SSL certificates
- Enable Windows high DPI support
- Handle multiprocessing freeze support
- Configure async event loop
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """Check if running as frozen executable"""
    return getattr(sys, "frozen", False)


def get_meipass() -> Path | None:
    """Get PyInstaller temp directory path"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return None


def fix_pkg_resources():
    """
    Fix pkg_resources/jaraco import issues in frozen environment.
    إصلاح مشاكل استيراد pkg_resources/jaraco في التطبيق المجمّع
    """
    if not is_frozen():
        return

    import types

    # Create dummy modules for missing jaraco submodules
    jaraco_modules = [
        "jaraco",
        "jaraco.text",
        "jaraco.functools",
        "jaraco.context",
        "jaraco.classes",
        "jaraco.collections",
    ]

    for mod_name in jaraco_modules:
        if mod_name not in sys.modules:
            try:
                __import__(mod_name)
            except ImportError:
                # Create dummy module
                dummy = types.ModuleType(mod_name)
                sys.modules[mod_name] = dummy

                # Add common attributes
                if mod_name == "jaraco.text":
                    dummy.strip_prefix = lambda s, p: s[len(p) :] if s.startswith(p) else s
                    dummy.strip_suffix = lambda s, p: s[: -len(p)] if s.endswith(p) else s
                elif mod_name == "jaraco.functools":
                    dummy.once = lambda f: f
                    dummy.method_cache = lambda f: f
                elif mod_name == "jaraco.context":
                    dummy.suppress = lambda *a: None


def fix_multiprocessing():
    """
    Fix multiprocessing for frozen executable.
    إصلاح المعالجة المتعددة للتطبيق المجمّع
    """
    if not is_frozen():
        return

    # Set multiprocessing start method
    try:
        import multiprocessing

        if sys.platform == "win32":
            # Windows requires spawn
            multiprocessing.set_start_method("spawn", force=True)
        else:
            # Unix can use fork or spawn
            try:
                multiprocessing.set_start_method("fork", force=True)
            except ValueError:
                multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method already set
        pass

    # Support freeze on Windows
    if sys.platform == "win32":
        try:
            import multiprocessing.freeze_support

            multiprocessing.freeze_support()
        except Exception:
            pass


def setup_qt_environment():
    """
    Setup Qt environment variables for frozen application.
    إعداد متغيرات بيئة Qt للتطبيق المجمّع
    """
    if not is_frozen():
        return

    meipass = get_meipass()
    if not meipass:
        return

    # Qt plugins path
    qt_paths = [
        meipass / "PySide6" / "plugins",
        meipass / "PySide6" / "Qt" / "plugins",
        meipass / "qt6_plugins",
    ]

    for qt_plugins in qt_paths:
        if qt_plugins.exists():
            os.environ["QT_PLUGIN_PATH"] = str(qt_plugins)
            break

    # Qt QML path
    qml_paths = [
        meipass / "PySide6" / "qml",
        meipass / "PySide6" / "Qt" / "qml",
    ]

    for qt_qml in qml_paths:
        if qt_qml.exists():
            os.environ["QML2_IMPORT_PATH"] = str(qt_qml)
            break

    # Prevent Qt debug messages in production
    if not os.environ.get("QT_DEBUG"):
        os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.*.debug=false"


def setup_ssl_certificates():
    """
    Setup SSL certificates for HTTPS connections.
    إعداد شهادات SSL لاتصالات HTTPS
    """
    if not is_frozen():
        return

    meipass = get_meipass()
    if not meipass:
        return

    # Try to find certificates
    cert_paths = [
        meipass / "certifi" / "cacert.pem",
        meipass / "lib" / "certifi" / "cacert.pem",
        meipass / "cacert.pem",
    ]

    for ssl_cert in cert_paths:
        if ssl_cert.exists():
            os.environ["SSL_CERT_FILE"] = str(ssl_cert)
            os.environ["REQUESTS_CA_BUNDLE"] = str(ssl_cert)
            os.environ["CURL_CA_BUNDLE"] = str(ssl_cert)
            break


def setup_windows_environment():
    """
    Setup Windows-specific environment.
    إعداد بيئة Windows الخاصة
    """
    if sys.platform != "win32":
        return

    # Enable high DPI support
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    # Enable Windows dark mode detection
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=2")

    # Fix encoding for console output
    try:
        import io

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        else:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

    # Suppress subprocess console window
    if is_frozen():
        try:
            import subprocess

            # Create startup info to hide console
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            # Monkey-patch Popen to use our settings
            original_popen = subprocess.Popen

            def patched_popen(*args, **kwargs):
                if "startupinfo" not in kwargs and sys.platform == "win32":
                    kwargs["startupinfo"] = si
                    kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
                return original_popen(*args, **kwargs)

            subprocess.Popen = patched_popen
        except Exception:
            pass


def setup_macos_environment():
    """
    Setup macOS-specific environment.
    إعداد بيئة macOS الخاصة
    """
    if sys.platform != "darwin":
        return

    # Enable retina display support
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

    # Fix for dark mode
    os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")


def setup_linux_environment():
    """
    Setup Linux-specific environment.
    إعداد بيئة Linux الخاصة
    """
    if sys.platform not in ("linux", "linux2"):
        return

    # Use xcb platform by default
    if "DISPLAY" in os.environ:
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    elif "WAYLAND_DISPLAY" in os.environ:
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")

    # Fix for some Linux distributions
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")


def setup_asyncio():
    """
    Setup asyncio for Qt integration.
    إعداد asyncio للتكامل مع Qt
    """
    if not is_frozen():
        return

    # Windows needs special event loop policy
    if sys.platform == "win32":
        try:
            import asyncio

            # Use selector event loop on Windows for better compatibility
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


def add_package_paths():
    """
    Add package paths to sys.path for frozen application.
    إضافة مسارات الحزم إلى sys.path للتطبيق المجمّع
    """
    if not is_frozen():
        return

    meipass = get_meipass()
    if not meipass:
        return

    # Add paths that might be needed
    paths_to_add = [
        meipass,
        meipass / "lib",
        meipass / "distributed_cluster",
    ]

    for path in paths_to_add:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)


# ══════════════════════════════════════════════════════════════════
# Run all setup functions when hook is loaded
# ══════════════════════════════════════════════════════════════════


def _run_hooks():
    """Run all runtime hooks in order"""
    # Fix imports first
    fix_pkg_resources()
    fix_multiprocessing()

    # Add paths
    add_package_paths()

    # Setup environment
    setup_qt_environment()
    setup_ssl_certificates()
    setup_asyncio()

    # Platform-specific setup
    setup_windows_environment()
    setup_macos_environment()
    setup_linux_environment()


# Execute hooks immediately
_run_hooks()
