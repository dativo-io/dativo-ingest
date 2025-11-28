#!/bin/bash
# Check Docker configuration for sandbox tests
# Verifies that Docker is properly configured to run sandboxed containers

set +e  # Don't exit on error - we want to report all issues

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Track issues
ISSUES=0
WARNINGS=0

echo -e "${BLUE}🔍 Checking Docker configuration for sandbox tests...${NC}"
echo ""

# Check 1: Docker is installed
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "   Install Docker: https://www.docker.com/products/docker-desktop"
    ISSUES=$((ISSUES + 1))
    exit 1
fi
echo -e "${GREEN}✅ Docker is installed${NC}"

# Check 2: Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    echo "   Start Docker Desktop or: sudo systemctl start docker"
    ISSUES=$((ISSUES + 1))
    exit 1
fi
echo -e "${GREEN}✅ Docker daemon is running${NC}"

# Check 3: Docker can pull images
echo -n "   Checking Docker image pull capability... "
if docker pull python:3.10 >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: Cannot pull images (may be network issue or rate limit)"
    echo "   Tests will use cached images if available"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 4: Test basic container creation
echo -n "   Testing basic container creation... "
TEST_CONTAINER="dativo-docker-check-$$"
if docker run --rm --name "$TEST_CONTAINER" python:3.10 echo "test" >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${RED}❌${NC}"
    echo "   Error: Cannot create basic containers"
    ISSUES=$((ISSUES + 1))
fi

# Check 5: Test read-only filesystem support
echo -n "   Testing read-only filesystem support... "
if docker run --rm --read-only python:3.10 echo "test" >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: Read-only filesystem may not be supported"
    echo "   Sandbox will work but with reduced security"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 6: Test tmpfs support
echo -n "   Testing tmpfs support... "
if docker run --rm --tmpfs /tmp:size=100m python:3.10 ls /tmp >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: tmpfs may not be supported"
    echo "   Sandbox will work but with reduced security"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 7: Test volume mount support
echo -n "   Testing volume mount support... "
TEMP_DIR=$(mktemp -d 2>/dev/null || echo "/tmp/dativo-test-$$")
mkdir -p "$TEMP_DIR"
echo "test" > "$TEMP_DIR/test.txt"
chmod 755 "$TEMP_DIR" 2>/dev/null || true
if docker run --rm -v "$TEMP_DIR:/test:ro" python:3.10 cat /test/test.txt >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
    rm -rf "$TEMP_DIR" 2>/dev/null || true
else
    # Try with absolute path
    ABS_TEMP_DIR=$(cd "$TEMP_DIR" && pwd)
    if docker run --rm -v "$ABS_TEMP_DIR:/test:ro" python:3.10 cat /test/test.txt >/dev/null 2>&1; then
        echo -e "${GREEN}✅${NC}"
        rm -rf "$TEMP_DIR" 2>/dev/null || true
    else
        echo -e "${YELLOW}⚠️${NC}"
        echo "   Warning: Volume mounts may have issues (check Docker settings)"
        echo "   Sandbox will attempt to work but may fail on volume mounts"
        rm -rf "$TEMP_DIR" 2>/dev/null || true
        WARNINGS=$((WARNINGS + 1))
    fi
fi

# Check 8: Test seccomp support (optional, but preferred)
echo -n "   Testing seccomp profile support... "
# Create minimal seccomp profile
TEMP_SECCOMP=$(mktemp)
cat > "$TEMP_SECCOMP" << 'EOF'
{
  "defaultAction": "SCMP_ACT_ALLOW",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": []
}
EOF

if docker run --rm --security-opt "seccomp=$TEMP_SECCOMP" python:3.10 echo "test" >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: Custom seccomp profiles may not be supported"
    echo "   Sandbox will work but will retry without seccomp if needed"
    WARNINGS=$((WARNINGS + 1))
fi
rm -f "$TEMP_SECCOMP"

# Check 9: Test network isolation
echo -n "   Testing network isolation support... "
if docker run --rm --network none python:3.10 echo "test" >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: Network isolation may not be supported"
    echo "   Sandbox will work but with network access enabled"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 10: Test resource limits
echo -n "   Testing resource limits support... "
if docker run --rm --memory="128m" --cpus="0.5" python:3.10 echo "test" >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
else
    echo -e "${YELLOW}⚠️${NC}"
    echo "   Warning: Resource limits may not be fully supported"
    echo "   Sandbox will work but limits may not be enforced"
    WARNINGS=$((WARNINGS + 1))
fi

# Check 11: Check Docker runtime (runc vs others)
echo -n "   Checking Docker runtime... "
RUNTIME=$(docker info 2>/dev/null | grep -i "Default Runtime" | awk '{print $3}' || echo "unknown")
if [ "$RUNTIME" = "runc" ] || [ "$RUNTIME" = "default" ]; then
    echo -e "${GREEN}✅ ($RUNTIME)${NC}"
else
    echo -e "${YELLOW}⚠️  ($RUNTIME)${NC}"
    echo "   Warning: Using non-standard runtime ($RUNTIME)"
    echo "   Some features may not work as expected"
    WARNINGS=$((WARNINGS + 1))
fi

# Summary
echo ""
if [ $ISSUES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ Docker is properly configured for sandbox tests${NC}"
    exit 0
elif [ $ISSUES -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Docker configuration has $WARNINGS warning(s)${NC}"
    echo "   Sandbox tests should work but some features may be limited"
    exit 0
else
    echo -e "${RED}❌ Docker configuration has $ISSUES critical issue(s)${NC}"
    echo "   Please fix the issues above before running sandbox tests"
    exit 1
fi

