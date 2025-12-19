"""
Build Script for NebulaCompute Desktop
سكريبت بناء تطبيق سطح المكتب

Usage:
    python build_exe.py

Requirements:
    pip install pyinstaller

This will create a standalone Windows executable in the 'dist' folder.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def get_project_root():
    """Get project root directory"""
    return Path(__file__).parent.parent.parent.parent


def clean_build():
    """Clean previous build artifacts"""
    project_root = get_project_root()

    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"Cleaning {dir_path}...")
            shutil.rmtree(dir_path)

    # Clean .spec file
    spec_file = project_root / 'NebulaCompute.spec'
    if spec_file.exists():
        spec_file.unlink()


def build_exe():
    """Build the executable using PyInstaller"""
    project_root = get_project_root()
    desktop_path = project_root / 'src' / 'distributed_cluster' / 'desktop'
    main_script = desktop_path / 'main.py'

    # Icon path (create if needed)
    icon_path = desktop_path / 'resources' / 'icon.ico'

    # PyInstaller options
    # On Windows, use ';' as separator, on Unix use ':'
    data_sep = ';' if sys.platform == 'win32' else ':'

    options = [
        'pyinstaller',
        '--name=NebulaCompute',
        '--windowed',  # No console window
        '--onefile',   # Single executable
        '--clean',     # Clean cache

        # Add data files (use platform-appropriate separator)
        f'--add-data={desktop_path / "resources"}{data_sep}resources',

        # Hidden imports for PySide6
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=PySide6.QtCharts',
        '--hidden-import=qasync',
        '--hidden-import=httpx',
        '--hidden-import=websockets',

        # Exclude unnecessary modules to reduce size
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=numpy',
        '--exclude-module=pandas',
        '--exclude-module=scipy',
        '--exclude-module=PIL',

        # Output directory
        f'--distpath={project_root / "dist"}',
        f'--workpath={project_root / "build"}',
        f'--specpath={project_root}',
    ]

    # Add icon if exists
    if icon_path.exists():
        options.append(f'--icon={icon_path}')

    # Add main script
    options.append(str(main_script))

    print("Building NebulaCompute Desktop...")
    print(f"Command: {' '.join(options)}")

    # Run PyInstaller
    result = subprocess.run(options, cwd=project_root)

    if result.returncode == 0:
        print("\n" + "="*50)
        print("Build successful!")
        print(f"Executable location: {project_root / 'dist' / 'NebulaCompute.exe'}")
        print("="*50)
    else:
        print("\nBuild failed!")
        sys.exit(1)


def create_installer_script():
    """Create NSIS installer script for Windows"""
    project_root = get_project_root()

    nsis_script = '''
; NebulaCompute Desktop Installer
; NSIS Installer Script

!include "MUI2.nsh"

; General
Name "NebulaCompute Desktop"
OutFile "NebulaCompute_Setup.exe"
InstallDir "$PROGRAMFILES\\NebulaCompute"
RequestExecutionLevel admin

; Interface
!define MUI_ABORTWARNING
!define MUI_ICON "src\\distributed_cluster\\desktop\\resources\\icon.ico"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Languages
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Arabic"

; Installer Section
Section "Install"
    SetOutPath $INSTDIR

    ; Copy files
    File "dist\\NebulaCompute.exe"

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\NebulaCompute"
    CreateShortCut "$SMPROGRAMS\\NebulaCompute\\NebulaCompute.lnk" "$INSTDIR\\NebulaCompute.exe"
    CreateShortCut "$DESKTOP\\NebulaCompute.lnk" "$INSTDIR\\NebulaCompute.exe"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry entries
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "DisplayName" "NebulaCompute Desktop"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute" \\
        "UninstallString" "$INSTDIR\\Uninstall.exe"
SectionEnd

; Uninstaller Section
Section "Uninstall"
    Delete "$INSTDIR\\NebulaCompute.exe"
    Delete "$INSTDIR\\Uninstall.exe"

    Delete "$SMPROGRAMS\\NebulaCompute\\NebulaCompute.lnk"
    Delete "$DESKTOP\\NebulaCompute.lnk"
    RMDir "$SMPROGRAMS\\NebulaCompute"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\NebulaCompute"
SectionEnd
'''

    nsis_path = project_root / 'installer.nsi'
    with open(nsis_path, 'w') as f:
        f.write(nsis_script)

    print(f"NSIS installer script created: {nsis_path}")


def main():
    """Main build function"""
    import argparse

    parser = argparse.ArgumentParser(description='Build NebulaCompute Desktop')
    parser.add_argument('--clean', action='store_true', help='Clean build artifacts only')
    parser.add_argument('--installer', action='store_true', help='Create NSIS installer script')
    args = parser.parse_args()

    if args.clean:
        clean_build()
        print("Build cleaned.")
        return

    if args.installer:
        create_installer_script()
        return

    # Check for PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])

    # Clean and build
    clean_build()
    build_exe()


if __name__ == '__main__':
    main()
