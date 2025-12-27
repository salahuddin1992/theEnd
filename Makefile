# NebulaCompute Build System
# نظام بناء NebulaCompute
#
# Usage:
#   make build          - Build with auto-detection
#   make build-fast     - Quick build with PyInstaller
#   make build-optimized - Optimized build with Nuitka
#   make installer      - Create installer for current platform
#   make release        - Full release build
#   make clean          - Clean build artifacts
#
# New unified build script:
#   python build.py                 - Default release build
#   python build.py --mode debug    - Debug build
#   python build.py --installer nsis - With installer

PYTHON := python3
BUILDER := build.py
SMART_BUILDER := src/distributed_cluster/desktop/smart_builder.py
VERSION := $(shell git describe --tags --always 2>/dev/null || echo "1.0.0")

.PHONY: help build build-fast build-optimized build-nuitka installer release clean install-deps test

help:
	@echo "╔════════════════════════════════════════════════════════════╗"
	@echo "║         NebulaCompute Build System                        ║"
	@echo "║         نظام بناء NebulaCompute                            ║"
	@echo "╠════════════════════════════════════════════════════════════╣"
	@echo "║  make build          - Auto-detect best build method      ║"
	@echo "║  make build-fast     - Quick build (PyInstaller)          ║"
	@echo "║  make build-optimized - Optimized (Nuitka + LTO)          ║"
	@echo "║  make installer      - Create platform installer          ║"
	@echo "║  make release        - Full release build                 ║"
	@echo "║  make clean          - Clean build artifacts              ║"
	@echo "║  make install-deps   - Install build dependencies         ║"
	@echo "║  make test           - Run tests                          ║"
	@echo "╚════════════════════════════════════════════════════════════╝"

# Install build dependencies
install-deps:
	@echo "📦 Installing build dependencies..."
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install pyinstaller nuitka pyside6 qasync httpx websockets
	$(PYTHON) -m pip install -e .
	@echo "✅ Dependencies installed!"

# Auto-detect best build method
build:
	@echo "🚀 Building NebulaCompute (auto-detect)..."
	$(PYTHON) $(BUILDER) --mode release --version $(VERSION)

# Quick build with PyInstaller
build-fast:
	@echo "⚡ Quick build with PyInstaller..."
	$(PYTHON) $(BUILDER) --mode release --version $(VERSION)

# Optimized build with balanced settings
build-optimized:
	@echo "🔧 Optimized build..."
	$(PYTHON) $(BUILDER) --mode full --version $(VERSION)

# Build with Nuitka (best performance, slower build)
build-nuitka:
	@echo "🎯 Building with Nuitka (this takes a while)..."
	$(PYTHON) $(SMART_BUILDER) build --compiler nuitka --optimize max --version $(VERSION)

# Extreme optimization (Nuitka + PGO)
build-extreme:
	@echo "🔥 Extreme optimization build..."
	$(PYTHON) $(SMART_BUILDER) build --compiler nuitka --optimize extreme --version $(VERSION)

# Create installer for current platform
installer:
ifeq ($(OS),Windows_NT)
	@echo "📦 Creating Windows installer..."
	$(PYTHON) $(BUILDER) --mode release --installer nsis --version $(VERSION)
else
	UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
	@echo "📦 Creating Linux AppImage..."
	$(PYTHON) $(BUILDER) --mode release --installer appimage --version $(VERSION)
else ifeq ($(UNAME_S),Darwin)
	@echo "📦 Creating macOS DMG..."
	$(PYTHON) $(BUILDER) --mode release --installer dmg --version $(VERSION)
endif
endif

# Full release build
release:
	@echo "🎉 Creating release build v$(VERSION)..."
	$(PYTHON) $(BUILDER) --mode full --version $(VERSION)

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	$(PYTHON) $(BUILDER) --clean
	rm -rf dist/ build/ *.spec
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Clean complete!"

# Run tests
test:
	@echo "🧪 Running tests..."
	$(PYTHON) -m pytest tests/ -v

# Show build info
info:
	@echo "📋 Build Information"
	@echo "===================="
	@echo "Version: $(VERSION)"
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Platform: $$(uname -s) ($$(uname -m))"

# Build all platforms (for CI)
build-all: build-fast
	@echo "✅ Build complete for current platform"

# Development build (with console for debugging)
build-dev:
	@echo "🔧 Development build (with console)..."
	$(PYTHON) $(BUILDER) --mode debug --console --version $(VERSION)-dev
