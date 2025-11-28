#!/bin/bash
# Smoke tests for sandboxed plugin execution

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== Running smoke tests for sandboxed plugins ==="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "WARNING: Docker not found. Skipping sandbox tests."
    exit 0
fi

# Test Python plugin in cloud mode (should be sandboxed)
echo ""
echo "--- Test 1: Python plugin in cloud mode (should be sandboxed) ---"
PYTHONPATH=src python3 << 'EOF'
import sys
import tempfile
from pathlib import Path
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig

# Create test plugin
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write("""
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="Sandboxed execution")
""")
    plugin_path = f.name

try:
    reader_class = PluginLoader.load_reader(plugin_path, mode="cloud")
    source_config = SourceConfig(type="test", connection={})
    reader = reader_class(source_config)
    
    # Check if it's sandboxed
    from dativo_ingest.sandboxed_plugin_wrapper import SandboxedReaderWrapper
    assert isinstance(reader, SandboxedReaderWrapper), "Reader should be sandboxed in cloud mode"
    
    # Execute check_connection
    result = reader.check_connection()
    assert result.success, "Connection check should succeed"
    
    print("✓ Python plugin sandboxing in cloud mode works")
except Exception as e:
    print(f"✗ Python plugin sandboxing failed: {e}")
    sys.exit(1)
finally:
    Path(plugin_path).unlink()
EOF

# Test Python plugin in self_hosted mode (should NOT be sandboxed)
echo ""
echo "--- Test 2: Python plugin in self_hosted mode (should NOT be sandboxed) ---"
PYTHONPATH=src python3 << 'EOF'
import sys
import tempfile
from pathlib import Path
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig

# Create test plugin
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write("""
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="Direct execution")
""")
    plugin_path = f.name

try:
    reader_class = PluginLoader.load_reader(plugin_path, mode="self_hosted")
    source_config = SourceConfig(type="test", connection={})
    reader = reader_class(source_config)
    
    # Check if it's NOT sandboxed
    from dativo_ingest.sandboxed_plugin_wrapper import SandboxedReaderWrapper
    assert not isinstance(reader, SandboxedReaderWrapper), "Reader should NOT be sandboxed in self_hosted mode"
    
    # Execute check_connection
    result = reader.check_connection()
    assert result.success, "Connection check should succeed"
    
    print("✓ Python plugin direct execution in self_hosted mode works")
except Exception as e:
    print(f"✗ Python plugin direct execution failed: {e}")
    sys.exit(1)
finally:
    Path(plugin_path).unlink()
EOF

# Test sandbox config override
echo ""
echo "--- Test 3: Sandbox config override ---"
PYTHONPATH=src python3 << 'EOF'
import sys
import tempfile
from pathlib import Path
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig

# Create test plugin
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
    f.write("""
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="OK")
""")
    plugin_path = f.name

try:
    plugin_config = {"sandbox": {"enabled": True}}
    sandbox_config = {"cpu_limit": 0.5, "memory_limit": "256m"}
    
    reader_class = PluginLoader.load_reader(
        plugin_path,
        mode="self_hosted",  # Would normally not sandbox
        sandbox_config=sandbox_config,
        plugin_config=plugin_config,
    )
    source_config = SourceConfig(type="test", connection={})
    reader = reader_class(source_config)
    
    # Should be sandboxed because config says enabled=True
    from dativo_ingest.sandboxed_plugin_wrapper import SandboxedReaderWrapper
    assert isinstance(reader, SandboxedReaderWrapper), "Reader should be sandboxed when config enabled=True"
    assert reader.sandbox_config == sandbox_config, "Sandbox config should be passed through"
    
    print("✓ Sandbox config override works")
except Exception as e:
    print(f"✗ Sandbox config override failed: {e}")
    sys.exit(1)
finally:
    Path(plugin_path).unlink()
EOF

echo ""
echo "=== All smoke tests passed ==="

