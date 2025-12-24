# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('/home/user/theEnd/src/distributed_cluster/desktop/resources', 'distributed_cluster/desktop/resources'), ('/home/user/theEnd/src/distributed_cluster/web/templates', 'distributed_cluster/web/templates'), ('/home/user/theEnd/src/distributed_cluster/web/static', 'distributed_cluster/web/static'), ('/home/user/theEnd/config', 'config')]
binaries = []
hiddenimports = ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtCharts', 'PySide6.QtNetwork', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets', 'qasync', 'asyncio', 'httpx', 'httpx._transports', 'httpx._transports.default', 'websockets', 'websockets.client', 'websockets.legacy', 'websockets.legacy.client', 'distributed_cluster', 'distributed_cluster.desktop', 'distributed_cluster.desktop.main', 'distributed_cluster.desktop.main_window', 'distributed_cluster.desktop.api', 'distributed_cluster.desktop.api.client', 'distributed_cluster.desktop.views', 'distributed_cluster.desktop.widgets', 'distributed_cluster.desktop.resources', 'distributed_cluster.models', 'distributed_cluster.models.job', 'distributed_cluster.models.worker', 'distributed_cluster.models.resources', 'distributed_cluster.core', 'distributed_cluster.core.config', 'json', 'datetime', 'dataclasses', 'enum', 'typing', 'pathlib', 'uuid', 'threading', 'queue', 'collections', 'ssl', 'certifi', 'anyio', 'anyio._backends', 'anyio._backends._asyncio', 'sniffio', 'h11', 'httpcore', 'jaraco', 'jaraco.text', 'jaraco.functools', 'jaraco.context', 'jaraco.classes', 'jaraco.collections', 'pkg_resources', 'pkg_resources.extern', 'importlib_metadata', 'importlib_resources', 'packaging', 'packaging.version', 'packaging.specifiers', 'packaging.requirements', 'packaging.markers', 'zipp', 'more_itertools']
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('httpx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('websockets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('jaraco')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pkg_resources')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['/home/user/theEnd/src/distributed_cluster/desktop/app_entry.py'],
    pathex=['/home/user/theEnd/src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'IPython', 'jupyter', 'notebook', 'pytest', 'pip', 'wheel', 'cryptography', 'cryptography.hazmat', 'cryptography.hazmat.backends', 'cryptography.hazmat.backends.openssl', 'docker', 'pynvml'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NebulaCompute',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['/home/user/theEnd/src/distributed_cluster/desktop/resources/icon.ico'],
)
