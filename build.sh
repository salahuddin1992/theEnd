#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║        NebulaCompute Build Script for Linux/macOS                ║
# ║        سكريبت البناء لنظام لينكس وماك                             ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# Usage:
#   ./build.sh                    # Default release build
#   ./build.sh --mode debug       # Debug build
#   ./build.sh --mode minimal     # Minimal build
#   ./build.sh --installer        # Build with installer
#   ./build.sh --clean            # Clean only
#   ./build.sh --help             # Show help
#
# Requirements:
#   - Python 3.10+
#   - pip
#   - PyInstaller (will be installed if missing)

set -e

# ══════════════════════════════════════════════════════════════════
# Colors / الألوان
# ══════════════════════════════════════════════════════════════════
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ══════════════════════════════════════════════════════════════════
# Configuration / الإعدادات
# ══════════════════════════════════════════════════════════════════
APP_NAME="NebulaCompute"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
SRC_PATH="$PROJECT_ROOT/src"
DESKTOP_PATH="$SRC_PATH/distributed_cluster/desktop"
DIST_PATH="$PROJECT_ROOT/dist"
BUILD_PATH="$PROJECT_ROOT/build"

# Default options
BUILD_MODE="release"
CREATE_INSTALLER=false
CLEAN_ONLY=false
SHOW_CONSOLE=false
ONE_FILE=true
VERSION=""

# ══════════════════════════════════════════════════════════════════
# Functions / الدوال
# ══════════════════════════════════════════════════════════════════

print_banner() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                                    ║${NC}"
    echo -e "${CYAN}║   ${BOLD}███╗   ██╗███████╗██████╗ ██╗   ██╗██╗      █████╗${NC}${CYAN}              ║${NC}"
    echo -e "${CYAN}║   ${BOLD}████╗  ██║██╔════╝██╔══██╗██║   ██║██║     ██╔══██╗${NC}${CYAN}             ║${NC}"
    echo -e "${CYAN}║   ${BOLD}██╔██╗ ██║█████╗  ██████╔╝██║   ██║██║     ███████║${NC}${CYAN}             ║${NC}"
    echo -e "${CYAN}║   ${BOLD}██║╚██╗██║██╔══╝  ██╔══██╗██║   ██║██║     ██╔══██║${NC}${CYAN}             ║${NC}"
    echo -e "${CYAN}║   ${BOLD}██║ ╚████║███████╗██████╔╝╚██████╔╝███████╗██║  ██║${NC}${CYAN}             ║${NC}"
    echo -e "${CYAN}║   ${BOLD}╚═╝  ╚═══╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝${NC}${CYAN}             ║${NC}"
    echo -e "${CYAN}║                                                                    ║${NC}"
    echo -e "${CYAN}║   ${YELLOW}PyInstaller Build Script v2.0${NC}${CYAN}                                 ║${NC}"
    echo -e "${CYAN}║   ${GREEN}نظام البناء المتكامل${NC}${CYAN}                                           ║${NC}"
    echo -e "${CYAN}║                                                                    ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

log_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_section() {
    echo ""
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${BOLD}${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --mode MODE       Build mode: debug, release (default), minimal, full"
    echo "  --version VER     Override version number"
    echo "  --installer       Create platform installer (AppImage/DEB)"
    echo "  --console         Show console window"
    echo "  --onedir          Create directory instead of single file"
    echo "  --clean           Clean build artifacts only"
    echo "  --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                          # Default release build"
    echo "  $0 --mode debug             # Debug build with console"
    echo "  $0 --mode minimal           # Minimal build (smaller)"
    echo "  $0 --installer              # Build with AppImage"
    echo "  $0 --clean                  # Clean only"
    echo ""
}

get_version() {
    if [ -n "$VERSION" ]; then
        echo "$VERSION"
        return
    fi

    # Try git
    if command -v git &> /dev/null && [ -d "$PROJECT_ROOT/.git" ]; then
        local git_version
        git_version=$(git describe --tags --always 2>/dev/null | sed 's/^v//')
        if [ -n "$git_version" ]; then
            echo "$git_version"
            return
        fi
    fi

    # Try pyproject.toml
    if [ -f "$PROJECT_ROOT/pyproject.toml" ]; then
        local toml_version
        toml_version=$(grep -E '^version\s*=' "$PROJECT_ROOT/pyproject.toml" | head -1 | sed 's/.*"\(.*\)".*/\1/')
        if [ -n "$toml_version" ]; then
            echo "$toml_version"
            return
        fi
    fi

    echo "1.0.0"
}

check_python() {
    log_section "Checking Python / فحص بايثون"

    # Check for python3
    if command -v python3 &> /dev/null; then
        PYTHON="python3"
    elif command -v python &> /dev/null; then
        PYTHON="python"
    else
        log_error "Python not found! Please install Python 3.10+"
        exit 1
    fi

    # Check version
    local py_version
    py_version=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_success "Python: $py_version"

    # Check if version is sufficient
    local major minor
    major=$($PYTHON -c "import sys; print(sys.version_info.major)")
    minor=$($PYTHON -c "import sys; print(sys.version_info.minor)")

    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 10 ]); then
        log_error "Python 3.10+ required, found $py_version"
        exit 1
    fi
}

check_dependencies() {
    log_section "Checking Dependencies / فحص التبعيات"

    # Check PyInstaller
    if $PYTHON -c "import PyInstaller" 2>/dev/null; then
        local pyinstaller_version
        pyinstaller_version=$($PYTHON -m PyInstaller --version 2>/dev/null || echo "unknown")
        log_success "PyInstaller: $pyinstaller_version"
    else
        log_warning "PyInstaller not found, installing..."
        $PYTHON -m pip install pyinstaller --quiet
        log_success "PyInstaller installed"
    fi

    # Check PySide6
    if $PYTHON -c "import PySide6" 2>/dev/null; then
        log_success "PySide6: installed"
    else
        log_warning "PySide6 not found, installing..."
        $PYTHON -m pip install PySide6 --quiet
        log_success "PySide6 installed"
    fi

    # Check other dependencies
    for dep in qasync httpx websockets; do
        if $PYTHON -c "import $dep" 2>/dev/null; then
            log_success "$dep: installed"
        else
            log_warning "$dep not found, installing..."
            $PYTHON -m pip install "$dep" --quiet
        fi
    done

    # Check UPX (optional)
    if command -v upx &> /dev/null; then
        log_success "UPX: available"
        UPX_AVAILABLE=true
    else
        log_info "UPX: not installed (optional)"
        UPX_AVAILABLE=false
    fi

    # Platform info
    local platform_name
    platform_name=$(uname -s)
    local arch
    arch=$(uname -m)
    log_success "Platform: $platform_name ($arch)"
}

clean_build() {
    log_section "Cleaning Build Artifacts / تنظيف ملفات البناء"

    if [ -d "$BUILD_PATH" ]; then
        log_info "Removing: $BUILD_PATH"
        rm -rf "$BUILD_PATH"
    fi

    if [ -d "$DIST_PATH" ]; then
        log_info "Removing: $DIST_PATH"
        rm -rf "$DIST_PATH"
    fi

    # Remove spec files
    for spec in "$PROJECT_ROOT"/*.spec; do
        if [ -f "$spec" ]; then
            log_info "Removing: $(basename "$spec")"
            rm -f "$spec"
        fi
    done

    # Remove pycache
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true

    log_success "Clean complete!"
}

build_executable() {
    log_section "Building Executable / بناء الملف التنفيذي"

    local version
    version=$(get_version)

    log_info "Name: $APP_NAME"
    log_info "Version: $version"
    log_info "Mode: $BUILD_MODE"

    # Find entry point
    local entry_point=""
    if [ -f "$DESKTOP_PATH/app_entry.py" ]; then
        entry_point="$DESKTOP_PATH/app_entry.py"
    elif [ -f "$DESKTOP_PATH/main.py" ]; then
        entry_point="$DESKTOP_PATH/main.py"
    else
        log_error "Entry point not found!"
        exit 1
    fi

    log_info "Entry point: $entry_point"

    # Build command
    local cmd="$PYTHON -m PyInstaller"
    cmd="$cmd --name=$APP_NAME"
    cmd="$cmd --clean"
    cmd="$cmd --noconfirm"

    # Console/windowed
    if [ "$SHOW_CONSOLE" = true ] || [ "$BUILD_MODE" = "debug" ]; then
        cmd="$cmd --console"
    else
        cmd="$cmd --windowed"
    fi

    # One file/directory
    if [ "$ONE_FILE" = true ]; then
        cmd="$cmd --onefile"
    else
        cmd="$cmd --onedir"
    fi

    # Icon
    local icon_path="$DESKTOP_PATH/resources/icon.ico"
    if [ -f "$icon_path" ]; then
        cmd="$cmd --icon=$icon_path"
    fi

    # Runtime hook
    if [ -f "$DESKTOP_PATH/runtime_hook.py" ]; then
        cmd="$cmd --runtime-hook=$DESKTOP_PATH/runtime_hook.py"
    fi

    # Data files
    local data_sep=":"

    if [ -d "$DESKTOP_PATH/resources" ]; then
        cmd="$cmd --add-data=$DESKTOP_PATH/resources${data_sep}distributed_cluster/desktop/resources"
    fi

    if [ -d "$SRC_PATH/distributed_cluster/web/templates" ]; then
        cmd="$cmd --add-data=$SRC_PATH/distributed_cluster/web/templates${data_sep}distributed_cluster/web/templates"
    fi

    if [ -d "$SRC_PATH/distributed_cluster/web/static" ]; then
        cmd="$cmd --add-data=$SRC_PATH/distributed_cluster/web/static${data_sep}distributed_cluster/web/static"
    fi

    if [ -d "$PROJECT_ROOT/config" ]; then
        cmd="$cmd --add-data=$PROJECT_ROOT/config${data_sep}config"
    fi

    # Hidden imports
    local hidden_imports=(
        "PySide6.QtCore"
        "PySide6.QtGui"
        "PySide6.QtWidgets"
        "PySide6.QtCharts"
        "PySide6.QtNetwork"
        "PySide6.QtSvg"
        "qasync"
        "asyncio"
        "httpx"
        "websockets"
        "distributed_cluster"
        "distributed_cluster.desktop"
        "distributed_cluster.desktop.main"
        "distributed_cluster.models"
        "distributed_cluster.core"
        "ssl"
        "certifi"
        "jaraco"
        "jaraco.text"
        "jaraco.functools"
        "pkg_resources"
    )

    for imp in "${hidden_imports[@]}"; do
        cmd="$cmd --hidden-import=$imp"
    done

    # Excludes
    local excludes=(
        "tkinter"
        "matplotlib"
        "numpy"
        "pandas"
        "scipy"
        "PIL"
        "IPython"
        "jupyter"
        "pytest"
    )

    for exc in "${excludes[@]}"; do
        cmd="$cmd --exclude-module=$exc"
    done

    # Collect all
    cmd="$cmd --collect-all=PySide6"
    cmd="$cmd --collect-all=httpx"
    cmd="$cmd --collect-all=websockets"

    # UPX
    if [ "$UPX_AVAILABLE" = false ]; then
        cmd="$cmd --noupx"
    fi

    # Strip
    cmd="$cmd --strip"

    # Paths
    cmd="$cmd --distpath=$DIST_PATH"
    cmd="$cmd --workpath=$BUILD_PATH"
    cmd="$cmd --specpath=$PROJECT_ROOT"
    cmd="$cmd --paths=$SRC_PATH"

    # Entry point
    cmd="$cmd $entry_point"

    log_info "Running PyInstaller..."
    echo ""

    # Execute
    eval "$cmd"

    # Check result
    local exe_path="$DIST_PATH/$APP_NAME"
    if [ -f "$exe_path" ]; then
        local size
        size=$(du -h "$exe_path" | cut -f1)

        log_section "Build Complete! / اكتمل البناء"
        echo ""
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║                     ✅ BUILD SUCCESSFUL!                          ║${NC}"
        echo -e "${GREEN}╠══════════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${GREEN}║  📁 Executable: $exe_path${NC}"
        echo -e "${GREEN}║  📊 Size: $size${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════════════╝${NC}"
        echo ""

        # Make executable
        chmod +x "$exe_path"

        log_info "To run: $exe_path"
    else
        log_error "Build failed! Executable not found."
        exit 1
    fi
}

create_appimage() {
    log_section "Creating AppImage / إنشاء AppImage"

    local version
    version=$(get_version)

    local exe_path="$DIST_PATH/$APP_NAME"
    if [ ! -f "$exe_path" ]; then
        log_error "Executable not found. Build first!"
        exit 1
    fi

    local appdir="$BUILD_PATH/${APP_NAME}.AppDir"
    mkdir -p "$appdir/usr/bin"

    # AppRun
    cat > "$appdir/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/NebulaCompute" "$@"
EOF
    chmod +x "$appdir/AppRun"

    # Desktop file
    cat > "$appdir/${APP_NAME}.desktop" << EOF
[Desktop Entry]
Name=${APP_NAME}
Comment=Distributed Computing System
Exec=${APP_NAME}
Icon=${APP_NAME,,}
Terminal=false
Type=Application
Categories=Development;Utility;
EOF

    # Copy executable
    cp "$exe_path" "$appdir/usr/bin/$APP_NAME"
    chmod +x "$appdir/usr/bin/$APP_NAME"

    # Download appimagetool if needed
    local appimagetool="$BUILD_PATH/appimagetool-x86_64.AppImage"
    if [ ! -f "$appimagetool" ]; then
        log_info "Downloading appimagetool..."
        curl -L -o "$appimagetool" \
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
        chmod +x "$appimagetool"
    fi

    # Build AppImage
    local output="$DIST_PATH/${APP_NAME}-${version}-x86_64.AppImage"
    ARCH=x86_64 "$appimagetool" "$appdir" "$output"

    if [ -f "$output" ]; then
        chmod +x "$output"
        log_success "Created: $output"
    else
        log_error "AppImage creation failed"
    fi
}

# ══════════════════════════════════════════════════════════════════
# Parse Arguments / تحليل المعاملات
# ══════════════════════════════════════════════════════════════════

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            BUILD_MODE="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --installer)
            CREATE_INSTALLER=true
            shift
            ;;
        --console)
            SHOW_CONSOLE=true
            shift
            ;;
        --onedir)
            ONE_FILE=false
            shift
            ;;
        --clean)
            CLEAN_ONLY=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# ══════════════════════════════════════════════════════════════════
# Main / الرئيسية
# ══════════════════════════════════════════════════════════════════

print_banner

if [ "$CLEAN_ONLY" = true ]; then
    clean_build
    exit 0
fi

check_python
check_dependencies
clean_build
build_executable

if [ "$CREATE_INSTALLER" = true ]; then
    local platform_name
    platform_name=$(uname -s)
    if [ "$platform_name" = "Linux" ]; then
        create_appimage
    else
        log_warning "Installer creation not supported on this platform"
    fi
fi

log_success "All done! / تم بنجاح!"
