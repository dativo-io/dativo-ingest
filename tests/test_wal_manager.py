"""Unit tests for WAL Manager."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.wal_manager import WALManager


class TestWALManager:
    """Test suite for WAL Manager."""

    def test_create_wal(self, tmp_path):
        """Test creating a new WAL file."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        wal_data = manager.create_wal(metadata={"extractor_type": "CSVExtractor"})

        assert wal_data["job_name"] == "test_job"
        assert wal_data["tenant_id"] == "test_tenant"
        assert wal_data["status"] == "in_progress"
        assert wal_data["version"] == "1.0"
        assert "created_at" in wal_data
        assert "updated_at" in wal_data
        assert wal_data["metadata"]["extractor_type"] == "CSVExtractor"
        assert manager.wal_file.exists()

    def test_load_wal(self, tmp_path):
        """Test loading an existing WAL file."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        # Create WAL first
        manager.create_wal()

        # Load it
        loaded_data = manager.load_wal()

        assert loaded_data["job_name"] == "test_job"
        assert loaded_data["status"] == "in_progress"
        assert manager.is_resuming()

    def test_update_checkpoint(self, tmp_path):
        """Test updating a checkpoint."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        checkpoint = {
            "type": "chunk_based",
            "chunk_number": 5,
            "records_in_chunk": 1000,
        }
        manager.update_checkpoint("stream1", checkpoint)

        loaded = manager.load_wal()
        assert "stream1" in loaded["checkpoints"]
        assert loaded["checkpoints"]["stream1"]["type"] == "chunk_based"
        assert loaded["checkpoints"]["stream1"]["chunk_number"] == 5

    def test_get_checkpoint(self, tmp_path):
        """Test getting a checkpoint."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        checkpoint = {
            "type": "offset_based",
            "last_offset": 50000,
        }
        manager.update_checkpoint("stream1", checkpoint)

        retrieved = manager.get_checkpoint("stream1")
        assert retrieved["type"] == "offset_based"
        assert retrieved["last_offset"] == 50000

        # Non-existent checkpoint
        assert manager.get_checkpoint("nonexistent") is None

    def test_get_resume_point(self, tmp_path):
        """Test getting resume point."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        checkpoint = {
            "type": "page_based",
            "last_page": 42,
        }
        manager.update_checkpoint("stream1", checkpoint)

        resume_point = manager.get_resume_point("stream1")
        assert resume_point["type"] == "page_based"
        assert resume_point["last_page"] == 42

    def test_finalize_wal(self, tmp_path):
        """Test finalizing WAL."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()
        manager.finalize_wal()

        loaded = manager.load_wal()
        assert loaded["status"] == "completed"
        assert "completed_at" in loaded
        assert manager.wal_final_file.exists()

    def test_cleanup_wal(self, tmp_path):
        """Test cleaning up WAL."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()
        manager.finalize_wal()
        manager.cleanup_wal()

        assert not manager.wal_file.exists()
        assert not manager.wal_final_file.exists()

    def test_is_resuming(self, tmp_path):
        """Test resume detection."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        # New WAL
        manager.create_wal()
        assert not manager.is_resuming()

        # Load existing WAL
        manager2 = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
            run_id=manager.run_id,
        )
        manager2.load_wal()
        assert manager2.is_resuming()

    def test_find_latest_wal(self, tmp_path):
        """Test finding latest WAL file."""
        wal_base_dir = tmp_path / "wal"
        tenant_id = "test_tenant"
        job_name = "test_job"

        # Create first WAL
        manager1 = WALManager(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
            run_id="20240101_100000",
        )
        manager1.create_wal()
        manager1.finalize_wal()  # Finalize so it's skipped

        # Create second WAL (not finalized)
        manager2 = WALManager(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
            run_id="20240101_110000",
        )
        manager2.create_wal()

        # Find latest
        latest = WALManager.find_latest_wal(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )

        assert latest is not None
        assert manager2.run_id in str(latest)

    def test_multiple_checkpoints(self, tmp_path):
        """Test managing multiple stream checkpoints."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Update checkpoints for multiple streams
        manager.update_checkpoint(
            "stream1",
            {"type": "chunk_based", "chunk_number": 10},
        )
        manager.update_checkpoint(
            "stream2",
            {"type": "page_based", "last_page": 5},
        )

        loaded = manager.load_wal()
        assert len(loaded["checkpoints"]) == 2
        assert loaded["checkpoints"]["stream1"]["chunk_number"] == 10
        assert loaded["checkpoints"]["stream2"]["last_page"] == 5

    def test_checkpoint_metadata(self, tmp_path):
        """Test checkpoint with metadata."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        checkpoint = {
            "type": "state_based",
            "airbyte_state": {"streams": []},
        }
        metadata = {"source": "airbyte", "version": "1.0"}
        manager.update_checkpoint("stream1", checkpoint, metadata=metadata)

        loaded = manager.load_wal()
        assert loaded["checkpoints"]["stream1"]["metadata"] == metadata

    def test_atomic_write(self, tmp_path):
        """Test that WAL writes are atomic."""
        wal_base_dir = tmp_path / "wal"
        manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )

        manager.create_wal()

        # Update checkpoint multiple times
        for i in range(10):
            manager.update_checkpoint(
                "stream1",
                {"type": "chunk_based", "chunk_number": i},
            )

        # Verify file is valid JSON
        with open(manager.wal_file, "r") as f:
            data = json.load(f)
            assert data["checkpoints"]["stream1"]["chunk_number"] == 9

    def test_resume_from_checkpoint(self, tmp_path):
        """Test resume scenario with checkpoint."""
        wal_base_dir = tmp_path / "wal"
        run_id = "20240101_120000"

        # Create WAL with checkpoint
        manager1 = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
            run_id=run_id,
        )
        manager1.create_wal()
        manager1.update_checkpoint(
            "stream1",
            {"type": "chunk_based", "chunk_number": 5},
        )

        # Resume with new manager instance
        manager2 = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
            run_id=run_id,
        )
        manager2.load_wal()

        resume_point = manager2.get_resume_point("stream1")
        assert resume_point["chunk_number"] == 5
        assert manager2.is_resuming()
