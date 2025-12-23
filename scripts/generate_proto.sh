#!/bin/bash
# ============================================================================
# Generate Python gRPC stubs from .proto files
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_ROOT/proto"
OUTPUT_DIR="$PROJECT_ROOT/src/distributed_cluster/grpc/generated"

echo "📦 Generating Python gRPC stubs..."
echo "   Proto dir: $PROTO_DIR"
echo "   Output dir: $OUTPUT_DIR"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Create __init__.py
cat > "$OUTPUT_DIR/__init__.py" << 'EOF'
"""
Generated gRPC stubs for NebulaCompute.

Auto-generated from proto/nebula.proto - DO NOT EDIT MANUALLY.
"""

from .nebula_pb2 import *
from .nebula_pb2_grpc import *

__all__ = [
    # Services
    "MasterServiceStub",
    "MasterServiceServicer",
    "ClientServiceStub",
    "ClientServiceServicer",
    "add_MasterServiceServicer_to_server",
    "add_ClientServiceServicer_to_server",
    # Messages - will be populated by imports
]
EOF

# Check for grpcio-tools
if ! python -c "import grpc_tools" 2>/dev/null; then
    echo "⚠️  grpcio-tools not installed. Installing..."
    pip install grpcio-tools
fi

# Generate Python files
python -m grpc_tools.protoc \
    -I"$PROTO_DIR" \
    --python_out="$OUTPUT_DIR" \
    --grpc_python_out="$OUTPUT_DIR" \
    "$PROTO_DIR/nebula.proto"

# Fix imports in generated files (relative imports for package structure)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    sed -i '' 's/import nebula_pb2/from . import nebula_pb2/' "$OUTPUT_DIR/nebula_pb2_grpc.py"
else
    # Linux
    sed -i 's/import nebula_pb2/from . import nebula_pb2/' "$OUTPUT_DIR/nebula_pb2_grpc.py"
fi

echo "✅ Generated files:"
ls -la "$OUTPUT_DIR"

echo ""
echo "🎉 Proto generation complete!"
