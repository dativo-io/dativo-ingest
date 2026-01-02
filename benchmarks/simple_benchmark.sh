#!/bin/bash
# Simple benchmark script to test Rust vs Python performance

set -e

echo "======================================================================"
echo "Simple Rust vs Python Performance Benchmark"
echo "======================================================================"
echo ""

# Configuration
RECORDS=${1:-100000}
BATCH_SIZE=${2:-10000}

echo "Configuration:"
echo "  Records:    $RECORDS"
echo "  Batch Size: $BATCH_SIZE"
echo ""

# Create temp directory
TEMP_DIR=$(mktemp -d)
echo "Output directory: $TEMP_DIR"
echo ""

# Run Python benchmark
echo "🐍 Running Python benchmark..."
START_PY=$(date +%s)
python3 benchmarks/benchmark_rust_vs_python.py \
    --records $RECORDS \
    --batch-size $BATCH_SIZE \
    --python-only \
    --output-dir "$TEMP_DIR/python" 2>&1 | grep -E "(Benchmark:|Records/Second|Duration|MB/Second)"
END_PY=$(date +%s)
DURATION_PY=$((END_PY - START_PY))
echo ""

# Check if Rust plugin exists
if [ -f "examples/plugins/rust/parquet_writer/target/release/libparquet_writer.so" ] || \
   [ -f "examples/plugins/rust/parquet_writer/target/release/libparquet_writer.dylib" ]; then
    echo "🦀 Running Rust benchmark..."
    START_RUST=$(date +%s)
    python3 benchmarks/benchmark_rust_vs_python.py \
        --records $RECORDS \
        --batch-size $BATCH_SIZE \
        --rust-only \
        --output-dir "$TEMP_DIR/rust" 2>&1 | grep -E "(Benchmark:|Records/Second|Duration|MB/Second)"
    END_RUST=$(date +%s)
    DURATION_RUST=$((END_RUST - START_RUST))
    echo ""
    
    # Calculate speedup
    if [ $DURATION_RUST -gt 0 ]; then
        SPEEDUP=$(echo "scale=2; $DURATION_PY / $DURATION_RUST" | bc)
        echo "======================================================================"
        echo "SUMMARY"
        echo "======================================================================"
        echo "Python Duration:  ${DURATION_PY}s"
        echo "Rust Duration:    ${DURATION_RUST}s"
        echo "Speedup:          ${SPEEDUP}x"
        echo ""
        
        if (( $(echo "$SPEEDUP > 1.0" | bc -l) )); then
            echo "✅ Rust is ${SPEEDUP}x FASTER than Python"
        else
            echo "⚠️  Python is faster (unexpected - check configuration)"
        fi
    fi
else
    echo "⚠️  Rust plugin not found. Build it with:"
    echo "   cd examples/plugins/rust && make build"
    echo ""
    echo "Running Python-only benchmark for now."
fi

echo ""
echo "📁 Results in: $TEMP_DIR"
echo ""
