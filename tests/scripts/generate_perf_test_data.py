#!/usr/bin/env python3
"""Generate 1GB CSV file for performance testing.

**DEPRECATED**: This script has been replaced by the Mimesis connector.
Use the job config instead:
    python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml

To generate a specific number of rows, edit the row_count in the job config or use:
    tests/fixtures/assets/mimesis/v1.0/perf_test_data.yaml

This legacy script is kept for backwards compatibility but may be removed in a future version.

Legacy Usage:
    python tests/scripts/generate_perf_test_data.py [--size-gb SIZE] [--output OUTPUT]
"""

import argparse
import csv
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


def generate_csv_file(output_path: Path, target_size_gb: float = 1.0):
    """Generate CSV file of approximately target_size_gb GB.

    Args:
        output_path: Path where CSV file should be written
        target_size_gb: Target size in GB (default: 1.0)
    """
    target_size_bytes = int(target_size_gb * 1024 * 1024 * 1024)

    # Columns matching perf_test_data asset schema
    columns = [
        "id",
        "name",
        "email",
        "department",
        "salary",
        "age",
        "city",
        "country",
        "status",
        "created_at",
    ]

    # Test data values
    departments = ["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations"]
    cities = ["New York", "London", "Tokyo", "San Francisco", "Berlin", "Paris"]
    countries = ["USA", "UK", "Japan", "Germany", "France"]
    statuses = ["active", "inactive", "pending"]

    row_count = 0
    bytes_written = 0

    print(f"Generating CSV file: {output_path}")
    print(f"Target size: {target_size_gb:.2f} GB ({target_size_bytes:,} bytes)")
    print("This may take a few minutes...")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        bytes_written += len(",".join(columns).encode("utf-8")) + 1

        while bytes_written < target_size_bytes:
            row_id = row_count + 1
            name = f"User_{row_id}"
            email = f"user{row_id}@example.com"
            department = departments[row_id % len(departments)]
            salary = 50000 + (row_id % 100000)
            age = 25 + (row_id % 40)
            city = cities[row_id % len(cities)]
            country = countries[row_id % len(countries)]
            status = statuses[row_id % len(statuses)]
            created_at = f"2024-01-{(row_id % 28) + 1:02d} 10:00:00"

            row = [
                row_id,
                name,
                email,
                department,
                salary,
                age,
                city,
                country,
                status,
                created_at,
            ]
            row_str = ",".join(str(x) for x in row)
            writer.writerow(row)

            bytes_written += len(row_str.encode("utf-8")) + 1
            row_count += 1

            # Progress updates every 100k rows
            if row_count % 100000 == 0:
                size_mb = bytes_written / (1024 * 1024)
                progress = (bytes_written / target_size_bytes) * 100
                print(
                    f"  Generated {row_count:,} rows ({size_mb:.2f} MB, {progress:.1f}%)..."
                )

    actual_size_mb = bytes_written / (1024 * 1024)
    actual_size_gb = bytes_written / (1024 * 1024 * 1024)

    print(f"\n✅ Generated {row_count:,} rows")
    print(f"   File size: {actual_size_mb:.2f} MB ({actual_size_gb:.3f} GB)")
    print(f"   Output: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate CSV file for performance testing"
    )
    parser.add_argument(
        "--size-gb", type=float, default=1.0, help="Target size in GB (default: 1.0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: tests/fixtures/seeds/perf_test_data_1gb.csv)",
    )

    args = parser.parse_args()

    if args.output:
        output_path = Path(args.output)
    else:
        # Default location in fixtures/seeds
        project_root = Path(__file__).parent.parent.parent
        output_path = (
            project_root / "tests" / "fixtures" / "seeds" / "perf_test_data_1gb.csv"
        )

    generate_csv_file(output_path, args.size_gb)


if __name__ == "__main__":
    main()
