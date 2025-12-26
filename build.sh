#!/bin/bash
# NebulaCompute Build Script for Linux/macOS
# سكربت بناء NebulaCompute لنظام لينكس/ماك
#
# Usage:
#   ./build.sh              - Default build
#   ./build.sh fast         - Quick build
#   ./build.sh optimized    - Optimized build
#   ./build.sh debug        - Debug build with console
#   ./build.sh clean        - Clean build artifacts
#   ./build.sh install      - Install dependencies
#   ./build.sh help         - Show help

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Header
echo ""
echo -e "${CYAN}${BOLD}======================================================${NC}"
echo -e "${CYAN}${BOLD}         NebulaCompute PyInstaller Builder            ${NC}"
echo -e "${CYAN}${BOLD}======================================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect Python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}Error: Python not found!${NC}"
    exit 1
fi

# Show help
show_help() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  (none)      Build with default settings"
    echo "  fast        Quick build with minimal optimization"
    echo "  optimized   Build with maximum optimization"
    echo "  debug       Debug build with console window"
    echo "  clean       Clean build artifacts"
    echo "  install     Install build dependencies"
    echo "  info        Show build configuration info"
    echo "  help        Show this help message"
    echo ""
    echo "Advanced options (pass directly to build.py):"
    echo "  --onedir    Create one-directory bundle"
    echo "  --console   Enable console window"
    echo "  --no-upx    Disable UPX compression"
    echo "  --strip     Strip debug symbols"
    echo "  --version X Override version string"
    echo "  --name X    Override output name"
    echo ""
    echo "Examples:"
    echo "  $0                        Default build"
    echo "  $0 fast                   Quick build"
    echo "  $0 --onedir --console     Custom options"
    echo ""
}

# Parse arguments
MODE="default"
ACTION="build"

case "$1" in
    "")
        ACTION="build"
        ;;
    fast|optimized|debug)
        MODE="$1"
        ;;
    clean)
        ACTION="clean"
        ;;
    install)
        ACTION="install"
        ;;
    info)
        ACTION="info"
        ;;
    help|-h|--help)
        show_help
        exit 0
        ;;
    *)
        # Pass through to build.py
        echo -e "${GREEN}Running with custom arguments...${NC}"
        $PYTHON build.py "$@"
        exit $?
        ;;
esac

# Execute action
case "$ACTION" in
    clean)
        echo -e "${YELLOW}Cleaning build artifacts...${NC}"
        $PYTHON build.py --clean
        ;;
    install)
        echo -e "${YELLOW}Installing dependencies...${NC}"
        $PYTHON build.py --install-deps
        ;;
    info)
        $PYTHON build.py --info
        ;;
    build)
        echo -e "${GREEN}Building with mode: ${MODE}${NC}"
        $PYTHON build.py --mode "$MODE"
        ;;
esac

# Check result
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}${BOLD}Done!${NC}"
else
    echo ""
    echo -e "${RED}${BOLD}Build failed!${NC}"
    exit 1
fi
