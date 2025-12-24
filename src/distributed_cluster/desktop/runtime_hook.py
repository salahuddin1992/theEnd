"""
PyInstaller Runtime Hook for NebulaCompute Desktop
خطاف التشغيل لـ PyInstaller

This hook runs before the main application starts.
يعمل هذا الخطاف قبل بدء التطبيق الرئيسي
"""

import os
import sys
from pathlib import Path


def setup_environment():
    """Setup environment for frozen application"""
    # Set Qt plugin path for frozen app
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = Path(sys._MEIPASS)

        # Qt plugins path
        qt_plugins = meipass / 'PySide6' / 'plugins'
        if qt_plugins.exists():
            os.environ['QT_PLUGIN_PATH'] = str(qt_plugins)

        # Qt QML path
        qt_qml = meipass / 'PySide6' / 'qml'
        if qt_qml.exists():
            os.environ['QML2_IMPORT_PATH'] = str(qt_qml)

        # SSL certificates (important for HTTPS)
        ssl_cert = meipass / 'certifi' / 'cacert.pem'
        if ssl_cert.exists():
            os.environ['SSL_CERT_FILE'] = str(ssl_cert)
            os.environ['REQUESTS_CA_BUNDLE'] = str(ssl_cert)

        # Windows-specific settings
        if sys.platform == 'win32':
            # Enable high DPI support
            os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
            os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

            # Suppress console for subprocess (prevents cmd window flash)
            import subprocess
            if hasattr(subprocess, 'STARTUPINFO'):
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE


# Run setup immediately when hook is loaded
setup_environment()
