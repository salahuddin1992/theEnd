"""
NebulaCompute Desktop Application Entry Point
نقطة الدخول الرئيسية لتطبيق سطح المكتب
"""

import sys
import asyncio
from typing import Optional

# Check for PySide6 availability
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QIcon
except ImportError:
    print("Error: PySide6 is not installed.")
    print("Install it with: pip install 'distributed-cluster[desktop]'")
    print("Or: pip install PySide6 qasync")
    sys.exit(1)

try:
    import qasync
except ImportError:
    print("Error: qasync is not installed.")
    print("Install it with: pip install qasync")
    sys.exit(1)

from .main_window import MainWindow


def setup_application() -> QApplication:
    """Setup Qt application with proper configuration"""
    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

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

    # Auto-connect if server URL provided
    if server_url:
        async def auto_connect():
            await window._connect_to_server(server_url, token or "")

        loop.create_task(auto_connect())

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
  dc-desktop                          # Launch the desktop application
  dc-desktop --server http://master:8765   # Connect to server on launch
  dc-desktop --server http://localhost:8765 --token mytoken

For more information, visit: https://github.com/nebulacompute/distributed-cluster
        """
    )

    parser.add_argument(
        "--server", "-s",
        type=str,
        help="Master server URL to connect to on startup (e.g., http://localhost:8765)",
        metavar="URL"
    )

    parser.add_argument(
        "--token", "-t",
        type=str,
        help="API token for authentication",
        metavar="TOKEN"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 0.1.0"
    )

    args = parser.parse_args()

    sys.exit(main(server_url=args.server, token=args.token))


if __name__ == "__main__":
    cli_main()
