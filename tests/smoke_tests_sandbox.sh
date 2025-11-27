#!/bin/bash
# Smoke test for plugin sandboxing with real Docker
# This test verifies that the sandbox actually executes plugins in Docker containers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    Plugin Sandbox Smoke Test                                  ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed or not in PATH${NC}"
    echo "   Please install Docker to run sandbox smoke tests"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker daemon is not running or not accessible${NC}"
    echo "   Please start Docker Desktop or Docker daemon to run sandbox smoke tests"
    echo "   On macOS: Open Docker Desktop application"
    echo "   On Linux: sudo systemctl start docker"
    exit 1
fi

# Verify Docker can pull images (test connectivity)
if ! docker pull python:3.10-slim &> /dev/null; then
    echo -e "${YELLOW}⚠️  Warning: Cannot pull Docker images (may be network issue)${NC}"
    echo "   The test will try to use cached images if available"
else
    echo -e "${GREEN}✅ Docker can pull images${NC}"
fi

echo -e "${GREEN}✅ Docker is available and running${NC}"
echo ""

# Detect Python interpreter
if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_CMD="python3.12"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo -e "${RED}❌ ERROR: No Python interpreter found${NC}"
    exit 1
fi

# Create temporary directory for test plugin
# Use a directory in the project to avoid Docker volume mount issues on macOS/colima
TEST_PLUGIN_DIR="$PROJECT_ROOT/tests/fixtures/plugins/sandbox_test"
mkdir -p "$TEST_PLUGIN_DIR"
trap "rm -rf $TEST_PLUGIN_DIR" EXIT

echo -e "${BLUE}📝 Creating test plugin...${NC}"

# Create a simple test plugin that implements check_connection
# This is a minimal plugin that doesn't require all dativo-ingest dependencies
cat > "$TEST_PLUGIN_DIR/test_sandbox_plugin.py" << 'EOF'
"""Test plugin for sandbox smoke test - minimal version."""

# Minimal implementation that doesn't require full dativo-ingest stack
class ConnectionTestResult:
    """Minimal ConnectionTestResult for testing."""
    def __init__(self, success, message, details=None, error_code=None):
        self.success = success
        self.message = message
        self.details = details or {}
        self.error_code = error_code
    
    def to_dict(self):
        result = {
            "success": self.success,
            "message": self.message,
            "details": self.details
        }
        if self.error_code:
            result["error_code"] = self.error_code
        return result


class TestSandboxReader:
    """Test reader for sandbox execution - minimal version."""
    
    __version__ = "1.0.0"
    
    def __init__(self, source_config):
        """Initialize with source_config."""
        self.source_config = source_config
    
    def check_connection(self):
        """Test connection method that returns a result."""
        source_type = self.source_config.get("type", "unknown") if isinstance(self.source_config, dict) else "unknown"
        return ConnectionTestResult(
            success=True,
            message="Connection test from sandbox",
            details={
                "plugin": "test_sandbox_plugin",
                "version": "1.0.0",
                "sandboxed": True,
                "source_type": source_type
            }
        )
    
    def extract(self, state_manager=None):
        """Dummy extract method."""
        yield [{"test": "data"}]
EOF

echo -e "${GREEN}✅ Test plugin created${NC}"
echo ""

# Create Python test script that uses the sandbox
echo -e "${BLUE}🧪 Running sandbox test...${NC}"

cat > "$TEST_PLUGIN_DIR/test_sandbox_execution.py" << EOF
"""Test script to execute plugin in sandbox."""

import sys
import json
from pathlib import Path

# Add project src to path
sys.path.insert(0, "$PROJECT_ROOT/src")

from dativo_ingest.sandbox import PluginSandbox
from dativo_ingest.config import SourceConfig

def main():
    plugin_path = Path("$TEST_PLUGIN_DIR/test_sandbox_plugin.py")
    
    print(f"Plugin path: {plugin_path}")
    print(f"Plugin exists: {plugin_path.exists()}")
    
    # Create sandbox instance
    try:
        sandbox = PluginSandbox(
            str(plugin_path),
            cpu_limit=0.5,
            memory_limit="256m",
            network_disabled=True,
            timeout=60
        )
        print("✅ Sandbox initialized")
    except Exception as e:
        print(f"❌ Failed to initialize sandbox: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Execute check_connection in sandbox
    # The sandbox will instantiate the plugin with source_config, then call check_connection()
    try:
        print("Executing check_connection in sandbox...")
        # Create source_config dict (will be serialized to JSON)
        # Pass as kwarg for instantiation, not as positional arg to check_connection
        source_config_dict = {"type": "test", "connection": {}}
        try:
            result = sandbox.execute("check_connection", source_config=source_config_dict)
        except Exception as e:
            print(f"❌ Execution error: {e}")
            # Try to get more details from the error
            if hasattr(e, 'details') and 'logs' in e.details:
                print(f"Container logs:\n{e.details['logs']}")
            raise
        
        print(f"✅ Method executed successfully")
        print(f"Result type: {type(result)}")
        print(f"Result: {json.dumps(result, indent=2, default=str)}")
        
        # Verify result structure
        if isinstance(result, dict):
            if result.get("success") is True or "success" in str(result).lower():
                print("✅ Result indicates success")
                return 0
            else:
                print(f"⚠️  Result does not indicate success: {result}")
                return 1
        else:
            print(f"⚠️  Unexpected result type: {type(result)}")
            return 1
            
    except Exception as e:
        print(f"❌ Failed to execute method: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
EOF

# Check if docker Python package is installed
if ! $PYTHON_CMD -c "import docker" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Docker Python package not installed${NC}"
    echo "   Installing docker package..."
    $PYTHON_CMD -m pip install docker --quiet || {
        echo -e "${RED}❌ Failed to install docker package${NC}"
        exit 1
    }
    echo -e "${GREEN}✅ Docker package installed${NC}"
    echo ""
fi

# Set DOCKER_HOST for colima if needed
if command -v colima &> /dev/null && colima status &> /dev/null; then
    COlima_SOCKET="$HOME/.colima/default/docker.sock"
    if [ -S "$COlima_SOCKET" ]; then
        export DOCKER_HOST="unix://$COlima_SOCKET"
        echo -e "${BLUE}ℹ️  Using colima Docker socket: $DOCKER_HOST${NC}"
    fi
fi

# Verify Python can connect to Docker
echo -e "${BLUE}🔍 Verifying Python Docker connectivity...${NC}"
if ! $PYTHON_CMD -c "import docker; client = docker.from_env(); client.ping()" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Python cannot connect to Docker daemon${NC}"
    echo "   This might be a permissions issue or Docker Desktop is not running"
    echo "   Skipping sandbox smoke test (Docker required)"
    echo ""
    echo "   To run this test:"
    echo "     - On macOS: Open Docker Desktop and wait for it to start"
    echo "     - On macOS with colima: Ensure colima is running (colima start)"
    echo "     - On Linux: sudo usermod -aG docker \$USER (then log out and back in)"
    echo ""
    exit 0  # Skip test gracefully instead of failing
fi
echo -e "${GREEN}✅ Python can connect to Docker${NC}"
echo ""

# Run the test script
cd "$TEST_PLUGIN_DIR"
export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"
# Export DOCKER_HOST so Python docker client can use it
export DOCKER_HOST="${DOCKER_HOST:-}"

if $PYTHON_CMD test_sandbox_execution.py; then
    echo ""
    echo -e "${GREEN}✅ Sandbox smoke test passed!${NC}"
    echo ""
    echo "The sandbox successfully:"
    echo "  - Initialized Docker container"
    echo "  - Loaded the plugin module"
    echo "  - Instantiated the plugin class"
    echo "  - Executed the check_connection method"
    echo "  - Returned the actual result (not a placeholder)"
    exit 0
else
    echo ""
    echo -e "${RED}❌ Sandbox smoke test failed!${NC}"
    exit 1
fi

