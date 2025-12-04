"""Infrastructure tests for WAL checkpointing system.

These tests verify that WAL infrastructure (directories, permissions, file structure)
is set up correctly and can handle various scenarios.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.wal_manager import WALManager


class TestWALInfrastructure:
    """Infrastructure tests for WAL system."""

    def test_wal_directory_creation(self, tmp_path):
        """Test that WAL directories are created correctly."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        # Create WAL (should create directory structure)
        manager.create_wal()

        # Verify directory structure
        assert wal_base_dir.exists()
        assert (wal_base_dir / "test_tenant").exists()
        assert (wal_base_dir / "test_tenant" / "test_job").exists()
        assert manager.wal_file.exists()

    def test_wal_directory_permissions(self, tmp_path):
        """Test that WAL directories have correct permissions."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Verify directory is writable
        assert os.access(wal_base_dir / "test_tenant" / "test_job", os.W_OK)
        assert os.access(manager.wal_file.parent, os.W_OK)

    def test_wal_file_permissions(self, tmp_path):
        """Test that WAL files have correct permissions."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Verify file is readable and writable
        assert os.access(manager.wal_file, os.R_OK)
        assert os.access(manager.wal_file, os.W_OK)

    def test_wal_concurrent_access(self, tmp_path):
        """Test that WAL can handle concurrent access scenarios."""
        wal_base_dir = tmp_path / "wal"
        manager1 = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
            run_id="run1",
        )
        manager2 = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
            run_id="run2",
        )

        # Create WAL files concurrently
        manager1.create_wal()
        manager2.create_wal()

        # Both should exist
        assert manager1.wal_file.exists()
        assert manager2.wal_file.exists()

        # Update checkpoints concurrently
        manager1.update_checkpoint(
            "stream1", {"type": "chunk_based", "chunk_number": 1}
        )
        manager2.update_checkpoint(
            "stream1", {"type": "chunk_based", "chunk_number": 2}
        )

        # Both should have valid checkpoints
        assert manager1.get_checkpoint("stream1") is not None
        assert manager2.get_checkpoint("stream1") is not None

    def test_wal_file_atomic_writes(self, tmp_path):
        """Test that WAL writes are atomic (no partial writes)."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Update checkpoint multiple times rapidly
        for i in range(10):
            manager.update_checkpoint(
                "stream1",
                {"type": "chunk_based", "chunk_number": i},
            )

        # File should always be valid JSON
        with open(manager.wal_file, "r") as f:
            data = json.load(f)
            assert data["checkpoints"]["stream1"]["chunk_number"] == 9

    def test_wal_cleanup_after_success(self, tmp_path):
        """Test that WAL files are cleaned up after successful completion."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()
        manager.update_checkpoint("stream1", {"type": "chunk_based", "chunk_number": 5})
        manager.finalize_wal()
        manager.cleanup_wal()

        # File should be removed
        assert not manager.wal_file.exists()

    def test_wal_persistence_after_failure(self, tmp_path):
        """Test that WAL files persist after failure (for resume)."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()
        manager.update_checkpoint("stream1", {"type": "chunk_based", "chunk_number": 5})

        # Simulate failure (don't finalize or cleanup)
        # WAL should still exist
        assert manager.wal_file.exists()

        # Should be able to resume
        resume_point = manager.get_resume_point("stream1")
        assert resume_point is not None
        assert resume_point["chunk_number"] == 5

    def test_wal_multiple_tenants(self, tmp_path):
        """Test that WAL supports multiple tenants."""
        wal_base_dir = tmp_path / "wal"

        manager1 = WALManager(
            job_name="job1",
            tenant_id="tenant1",
            wal_base_dir=str(wal_base_dir),
        )
        manager2 = WALManager(
            job_name="job1",
            tenant_id="tenant2",
            wal_base_dir=str(wal_base_dir),
        )

        manager1.create_wal()
        manager2.create_wal()

        # Both should have separate directories
        assert manager1.wal_file.exists()
        assert manager2.wal_file.exists()
        assert manager1.wal_file != manager2.wal_file

        # Verify tenant isolation
        assert "tenant1" in str(manager1.wal_file)
        assert "tenant2" in str(manager2.wal_file)

    def test_wal_multiple_jobs_same_tenant(self, tmp_path):
        """Test that WAL supports multiple jobs per tenant."""
        wal_base_dir = tmp_path / "wal"
        tenant_id = "test_tenant"

        manager1 = WALManager(
            job_name="job1",
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )
        manager2 = WALManager(
            job_name="job2",
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )

        manager1.create_wal()
        manager2.create_wal()

        # Both should exist
        assert manager1.wal_file.exists()
        assert manager2.wal_file.exists()

        # Should be in same tenant directory but different job directories
        assert manager1.wal_file.parent.parent == manager2.wal_file.parent.parent
        assert manager1.wal_file.parent != manager2.wal_file.parent

    def test_wal_file_size_limits(self, tmp_path):
        """Test that WAL handles large checkpoint data."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Create large checkpoint data
        large_state = {
            "type": "state_based",
            "airbyte_state": {
                "streams": [
                    {
                        "stream_descriptor": {"name": f"stream_{i}"},
                        "stream_state": {"cursor": f"value_{i}" * 100},
                    }
                    for i in range(100)
                ]
            },
        }

        manager.update_checkpoint("large_stream", large_state)

        # Should still be valid
        checkpoint = manager.get_checkpoint("large_stream")
        assert checkpoint is not None
        assert len(checkpoint["airbyte_state"]["streams"]) == 100

    def test_wal_find_latest_with_multiple_runs(self, tmp_path):
        """Test finding latest WAL when multiple runs exist."""
        wal_base_dir = tmp_path / "wal"
        job_name = "test_job"
        tenant_id = "test_tenant"

        # Create multiple WAL files
        runs = ["20240101_100000", "20240101_110000", "20240101_120000"]
        for run_id in runs:
            manager = WALManager(
                job_name=job_name,
                tenant_id=tenant_id,
                wal_base_dir=str(wal_base_dir),
                run_id=run_id,
            )
            manager.create_wal()
            # Finalize first two, leave last one active
            if run_id != runs[-1]:
                manager.finalize_wal()

        # Find latest should return the non-finalized one
        latest = WALManager.find_latest_wal(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )

        assert latest is not None
        assert runs[-1] in str(latest)
