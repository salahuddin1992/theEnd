#!/bin/bash
# ===============================================
# NebulaCompute Test Suite Runner
# سكريبت تشغيل اختبارات NebulaCompute
# ===============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
COVERAGE=false
PARALLEL=false
REPORT=false
VERBOSE=false
FAIL_FAST=false
TYPE="all"
MARKER=""
PATTERN=""

# Print header
echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════╗"
echo "║     🧪 NebulaCompute Test Suite               ║"
echo "║     نظام اختبارات NebulaCompute              ║"
echo "╚═══════════════════════════════════════════════╝"
echo -e "${NC}"

# Help message
show_help() {
    echo -e "${YELLOW}Usage:${NC} ./run_tests.sh [options]"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo "  --coverage, -c    Run with coverage reporting"
    echo "  --parallel, -p    Run tests in parallel"
    echo "  --report, -r      Generate HTML report"
    echo "  --verbose, -v     Verbose output"
    echo "  --fail-fast, -x   Stop on first failure"
    echo ""
    echo -e "${YELLOW}Test Types:${NC}"
    echo "  --unit            Run only unit tests"
    echo "  --integration     Run only integration tests"
    echo "  --security        Run only security tests"
    echo "  --performance     Run only performance tests"
    echo "  --fuzz            Run only fuzz tests"
    echo "  --all             Run all tests (default)"
    echo ""
    echo -e "${YELLOW}Filters:${NC}"
    echo "  --marker, -m      Run tests with specific marker"
    echo "  --pattern, -k     Run tests matching pattern"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  ./run_tests.sh --unit --coverage"
    echo "  ./run_tests.sh --all --parallel --report"
    echo "  ./run_tests.sh -k 'cache' -v"
    echo "  ./run_tests.sh -m 'slow' --coverage"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --parallel|-p)
            PARALLEL=true
            shift
            ;;
        --report|-r)
            REPORT=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --fail-fast|-x)
            FAIL_FAST=true
            shift
            ;;
        --unit)
            TYPE="unit"
            shift
            ;;
        --integration)
            TYPE="integration"
            shift
            ;;
        --security)
            TYPE="security"
            shift
            ;;
        --performance)
            TYPE="performance"
            shift
            ;;
        --fuzz)
            TYPE="fuzz"
            shift
            ;;
        --all)
            TYPE="all"
            shift
            ;;
        --marker|-m)
            MARKER="$2"
            shift 2
            ;;
        --pattern|-k)
            PATTERN="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Build pytest command
CMD="pytest"

# Select test directory based on type
case $TYPE in
    unit)
        CMD="$CMD tests/unit/"
        echo -e "${BLUE}📁 Running unit tests${NC}"
        ;;
    integration)
        CMD="$CMD tests/integration/"
        echo -e "${BLUE}📁 Running integration tests${NC}"
        ;;
    security)
        CMD="$CMD tests/security/"
        echo -e "${BLUE}📁 Running security tests${NC}"
        ;;
    performance)
        CMD="$CMD tests/performance/"
        echo -e "${BLUE}📁 Running performance tests${NC}"
        ;;
    fuzz)
        CMD="$CMD tests/fuzz/"
        echo -e "${BLUE}📁 Running fuzz tests${NC}"
        ;;
    all)
        CMD="$CMD tests/"
        echo -e "${BLUE}📁 Running all tests${NC}"
        ;;
esac

# Add verbosity
if $VERBOSE; then
    CMD="$CMD -v --tb=long"
else
    CMD="$CMD --tb=short"
fi

# Add fail-fast
if $FAIL_FAST; then
    CMD="$CMD -x"
fi

# Add coverage
if $COVERAGE; then
    CMD="$CMD --cov=src/distributed_cluster --cov-report=term-missing --cov-report=html"
    echo -e "${BLUE}📊 Coverage enabled${NC}"
fi

# Add parallel execution
if $PARALLEL; then
    CMD="$CMD -n auto"
    echo -e "${BLUE}⚡ Parallel execution enabled${NC}"
fi

# Add HTML report
if $REPORT; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CMD="$CMD --html=test_report_${TIMESTAMP}.html --self-contained-html"
    echo -e "${BLUE}📄 HTML report will be generated${NC}"
fi

# Add marker filter
if [[ -n "$MARKER" ]]; then
    CMD="$CMD -m '$MARKER'"
    echo -e "${BLUE}🏷️  Filtering by marker: $MARKER${NC}"
fi

# Add pattern filter
if [[ -n "$PATTERN" ]]; then
    CMD="$CMD -k '$PATTERN'"
    echo -e "${BLUE}🔍 Filtering by pattern: $PATTERN${NC}"
fi

# Add common options
CMD="$CMD --strict-markers -ra"

echo ""
echo -e "${YELLOW}Command: $CMD${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════${NC}"
echo ""

# Record start time
START_TIME=$(date +%s)

# Run tests
if eval $CMD; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}⏱️  Duration: ${DURATION}s${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════${NC}"

    # Open coverage report if generated
    if $COVERAGE; then
        echo ""
        echo -e "${CYAN}📊 Coverage report generated at: htmlcov/index.html${NC}"

        # Try to open in browser
        if [[ "$OSTYPE" == "darwin"* ]]; then
            open htmlcov/index.html 2>/dev/null || true
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            xdg-open htmlcov/index.html 2>/dev/null || true
        fi
    fi

    exit 0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    echo ""
    echo -e "${RED}═══════════════════════════════════════════════${NC}"
    echo -e "${RED}❌ Some tests failed!${NC}"
    echo -e "${RED}⏱️  Duration: ${DURATION}s${NC}"
    echo -e "${RED}═══════════════════════════════════════════════${NC}"

    exit 1
fi
