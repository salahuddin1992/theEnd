"""
NebulaCompute Desktop Application Entry Point for PyInstaller
نقطة الدخول للتطبيق المجمع

This file uses absolute imports to work with PyInstaller.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional


def get_resource_path(relative_path: str) -> Path:
    """
    Get the correct path for resources whether running as script or frozen exe.
    الحصول على المسار الصحيح للموارد سواء كان التطبيق يعمل كسكريبت أو ملف مجمّع
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running as PyInstaller bundle
        base_path = Path(sys._MEIPASS)
    else:
        # Running as normal script
        base_path = Path(__file__).parent
    return base_path / relative_path


def setup_frozen_environment():
    """
    Configure environment for frozen (PyInstaller) execution.
    تهيئة البيئة للتطبيق المجمّع
    """
    if getattr(sys, "frozen", False):
        # Set working directory to executable location
        exe_dir = Path(sys.executable).parent
        os.chdir(exe_dir)

        # Add the frozen base path to sys.path
        if hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)
            if str(meipass) not in sys.path:
                sys.path.insert(0, str(meipass))

        # Suppress Qt plugin debug messages
        os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

        # Set high DPI environment variables for Windows
        if sys.platform == "win32":
            os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
            os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")


# Setup frozen environment before any Qt imports
setup_frozen_environment()

# Check for PySide6 availability
try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QIcon  # noqa: F401
    from PySide6.QtWidgets import QApplication
except ImportError as e:
    error_msg = str(e)
    if "libEGL" in error_msg or "libGL" in error_msg or "xcb" in error_msg:
        print(f"Error: Missing graphics libraries: {error_msg}")
        print("This application requires a graphical environment (X11/Wayland).")
        print("On headless Linux, install: apt-get install libegl1 libxcb-xinerama0")
    else:
        print("Error: PySide6 is not installed or cannot be loaded.")
        print(f"Details: {error_msg}")
        print("Install it with: pip install PySide6 qasync")
    sys.exit(1)

try:
    import qasync
except ImportError:
    print("Error: qasync is not installed.")
    print("Install it with: pip install qasync")
    sys.exit(1)

# Use absolute imports for PyInstaller compatibility
from distributed_cluster.desktop.main_window import MainWindow


def setup_application() -> QApplication:
    """Setup Qt application with proper configuration"""
    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    # Application metadata
    app.setApplicationName("NebulaCompute Desktop")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("NebulaCompute")
    app.setOrganizationDomain("nebulacompute.io")

    # Set default font
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    return app


def main(server_url: Optional[str] = None, token: Optional[str] = None) -> int:
    """
    Main entry point for the desktop application.

    Args:
        server_url: Optional server URL to connect to on startup
        token: Optional API token for authentication

    Returns:
        Exit code
    """
    # Create application
    app = setup_application()

    # Create async event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create main window
    window = MainWindow()

    # Auto-connect if server URL provided, otherwise show connection dialog
    if server_url:
        window._server_name = server_url

        async def auto_connect():
            await window._connect_to_server(server_url, token or "")

        loop.create_task(auto_connect())
    else:
        # Show connection dialog on startup
        window.show_startup_dialog()

    # Show window
    window.show()

    # Run event loop
    with loop:
        return loop.run_forever()


def cli_main():
    """CLI entry point with argument parsing"""
    import argparse

    parser = argparse.ArgumentParser(
        description="NebulaCompute Desktop - Distributed Computing Management Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  NebulaCompute.exe                          # Launch the desktop application
  NebulaCompute.exe --server http://master:8765   # Connect to server on launch
        """,
    )

    parser.add_argument(
        "--server",
        "-s",
        type=str,
        help="Master server URL to connect to on startup",
        metavar="URL",
    )

    parser.add_argument("--token", "-t", type=str, help="API token for authentication", metavar="TOKEN")

    parser.add_argument("--version", "-v", action="version", version="%(prog)s 0.1.0")

    args = parser.parse_args()

    sys.exit(main(server_url=args.server, token=args.token))


if __name__ == "__main__":
    cli_main()
