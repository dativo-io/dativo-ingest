#!/bin/bash
# Setup script for local development and testing

# Don't exit on error - we want to continue even if some steps fail
set +e

echo "🚀 Setting up Dativo Ingestion Platform for local development..."

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check for Docker (supports Homebrew installation)
if command -v docker >/dev/null 2>&1; then
    DOCKER_CMD=$(command -v docker)
    echo "   Found Docker at: $DOCKER_CMD"
elif [ -f "/opt/homebrew/bin/docker" ]; then
    DOCKER_CMD="/opt/homebrew/bin/docker"
    echo "   Found Docker at: $DOCKER_CMD (Homebrew)"
    export PATH="/opt/homebrew/bin:$PATH"
else
    echo "❌ Docker is required but not installed. Aborting." >&2
    echo "   Install with: brew install docker" >&2
    exit 1
fi

# Check for docker-compose (supports Homebrew installation)
if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD=$(command -v docker-compose)
    echo "   Found docker-compose at: $DOCKER_COMPOSE_CMD"
elif [ -f "/opt/homebrew/bin/docker-compose" ]; then
    DOCKER_COMPOSE_CMD="/opt/homebrew/bin/docker-compose"
    echo "   Found docker-compose at: $DOCKER_COMPOSE_CMD (Homebrew)"
    export PATH="/opt/homebrew/bin:$PATH"
elif docker compose version >/dev/null 2>&1; then
    # Docker Compose V2 (plugin)
    DOCKER_COMPOSE_CMD="docker compose"
    echo "   Using Docker Compose V2 (plugin)"
else
    echo "❌ Docker Compose is required but not installed. Aborting." >&2
    echo "   Install with: brew install docker-compose" >&2
    exit 1
fi

# Check if Docker is running
if ! $DOCKER_CMD info >/dev/null 2>&1; then
    echo "⚠️  Docker daemon is not running."
    echo "   Please start Docker and run this script again."
    echo ""
    echo "   Options:"
    echo "   - Docker Desktop: open Docker Desktop application"
    echo "   - Colima: colima start"
    echo "   - Homebrew Docker: brew services start docker (if installed via Homebrew)"
    echo ""
    echo "   Continuing with setup (infrastructure will fail to start)..."
    DOCKER_NOT_RUNNING=1
else
    DOCKER_NOT_RUNNING=0
    echo "✅ Docker daemon is running"
fi

# Find Python 3.10+ or use python3
PYTHON_CMD="python3"
if command -v python3.10 >/dev/null 2>&1; then
    PYTHON_CMD="python3.10"
elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_CMD="python3.11"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_CMD="python3.12"
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_CMD="python3.13"
fi

# Check Python version
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "⚠️  Python 3.10+ is required, but found Python $PYTHON_VERSION"
    echo "   Attempting to install anyway (may fail)..."
    echo "   To use a different Python version, set PYTHON_CMD environment variable"
fi

echo "   Using: $PYTHON_CMD ($PYTHON_VERSION)"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
$PYTHON_CMD -m pip install --quiet --upgrade pip

# Install Python dependencies
echo "📦 Installing Python dependencies..."
$PYTHON_CMD -m pip install --quiet -r requirements.txt

# Try to install in editable mode, but don't fail if it doesn't work
EDITABLE_INSTALL_FAILED=0
$PYTHON_CMD -m pip install --quiet -e . 2>&1 | grep -v "requires a different Python" || {
    EDITABLE_INSTALL_FAILED=1
    echo "⚠️  Editable install failed (Python version issue), continuing anyway..."
    echo "   You can run commands with: PYTHONPATH=src $PYTHON_CMD -m dativo_ingest.cli"
}

# Start infrastructure
if [ "$DOCKER_NOT_RUNNING" -eq 0 ]; then
    echo "🐳 Starting local infrastructure (Nessie + MinIO)..."
    $DOCKER_COMPOSE_CMD -f docker-compose.dev.yml up -d
else
    echo "⚠️  Skipping infrastructure startup (Docker not running)"
fi

# Wait for services to be ready
if [ "$DOCKER_NOT_RUNNING" -eq 0 ]; then
    echo "⏳ Waiting for services to be ready..."
    sleep 5

    # Check Nessie
    echo "🔍 Checking Nessie..."
    NESSIE_READY=0
    for i in {1..30}; do
        if curl -sf http://localhost:19120/api/v1/config > /dev/null 2>&1; then
            echo "✅ Nessie is ready"
            NESSIE_READY=1
            break
        fi
        sleep 1
    done
    if [ $NESSIE_READY -eq 0 ]; then
        echo "⚠️  Nessie failed to start (may need more time or Docker issue)"
    fi

    # Check MinIO
    echo "🔍 Checking MinIO..."
    MINIO_READY=0
    for i in {1..30}; do
        if curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; then
            echo "✅ MinIO is ready"
            MINIO_READY=1
            break
        fi
        sleep 1
    done
    if [ $MINIO_READY -eq 0 ]; then
        echo "⚠️  MinIO failed to start (may need more time or Docker issue)"
    fi
else
    echo "⚠️  Skipping service health checks (Docker not running)"
fi

# Create MinIO bucket (if mc is available)
if command -v mc >/dev/null 2>&1; then
    echo "🪣 Creating MinIO bucket..."
    mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
    mc mb local/test-bucket 2>/dev/null || echo "⚠️  Bucket may already exist"
    echo "✅ Bucket created"
else
    echo "⚠️  MinIO client (mc) not found. Please create bucket manually:"
    echo "   mc alias set local http://localhost:9000 minioadmin minioadmin"
    echo "   mc mb local/test-bucket"
    echo "   Or use the web console at http://localhost:9001"
fi

# Create state directory (in .local to keep it out of repo)
echo "📁 Creating state directory..."
mkdir -p .local/state/test_tenant
echo "✅ State directory created at .local/state/"

# Export environment variables
echo "🔧 Setting up environment variables..."
export NESSIE_URI="http://localhost:19120/api/v1"
export S3_ENDPOINT="http://localhost:9000"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"
export AWS_REGION="us-east-1"
export S3_BUCKET="test-bucket"

# Save to .env file
cat > .env << EOF
NESSIE_URI=http://localhost:19120/api/v1
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
EOF

echo "✅ Environment variables saved to .env file"
echo ""
echo "✨ Setup complete!"
echo ""
if [ "$DOCKER_NOT_RUNNING" -eq 1 ]; then
    echo "⚠️  IMPORTANT: Docker is not running!"
    echo "   To complete setup, start Docker and run:"
    echo "   docker-compose -f docker-compose.dev.yml up -d"
    echo ""
fi
echo "📝 Next steps:"
echo "   1. Activate virtual environment:"
echo "      source venv/bin/activate"
echo ""
echo "   2. Source the environment variables:"
echo "      source .env"
echo "      # or: export \$(cat .env | xargs)"
echo ""
if [ "$DOCKER_NOT_RUNNING" -eq 1 ]; then
    echo "   3. Start Docker infrastructure:"
    echo "      $DOCKER_COMPOSE_CMD -f docker-compose.dev.yml up -d"
    echo "      # Wait ~30 seconds for services to be ready"
    echo ""
    echo "   4. Run the end-to-end test:"
else
    echo "   3. Run the end-to-end test:"
fi
if [ "$EDITABLE_INSTALL_FAILED" -eq 1 ]; then
    echo "      PYTHONPATH=src python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted"
else
    echo "      dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted"
    echo "      # or: PYTHONPATH=src python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted"
fi
echo ""
echo "   5. Or use the Makefile:"
echo "      make test-smoke"
echo ""
echo "🔗 Useful links:"
echo "   - Nessie API: http://localhost:19120/api/v1"
echo "   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo ""

