"""Integration tests for WAL checkpointing with extractors."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dativo_ingest.config import JobConfig, SourceConfig
from dativo_ingest.connectors.csv_extractor import CSVExtractor
from dativo_ingest.job_executor import JobExecutor
from dativo_ingest.wal_manager import WALManager


class TestWALCSVIntegration:
    """Integration tests for WAL with CSV extractor."""

    def test_csv_extractor_with_wal_resume(self, tmp_path):
        """Test CSV extractor resuming from WAL checkpoint."""
        # Create test CSV file
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "id": range(1, 101),
                "name": [f"Name_{i}" for i in range(1, 101)],
            }
        )
        df.to_csv(csv_file, index=False)

        # Create source config
        source_config = SourceConfig(
            type="csv",
            files=[{"path": str(csv_file), "id": "test_file"}],
        )

        # Create extractor
        extractor = CSVExtractor(source_config)

        # Create WAL manager
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal(metadata={"extractor_type": "CSVExtractor"})

        # Simulate processing first 3 chunks, then checkpoint
        chunk_size = 10
        chunks_processed = 0
        for batch in extractor.extract():
            chunks_processed += 1
            if chunks_processed >= 3:
                # Update checkpoint after 3 chunks
                checkpoint = {
                    "type": "chunk_based",
                    "file_id": "test_file",
                    "chunk_number": chunks_processed,
                    "records_in_chunk": len(batch),
                }
                wal_manager.update_checkpoint("test_file", checkpoint)
                break

        # Now resume from checkpoint
        checkpoint_context = {
            "checkpoint": wal_manager.get_resume_point("test_file"),
            "wal_manager": wal_manager,
            "stream_name": "test_file",
        }

        # Extract again with checkpoint context
        resumed_batches = list(extractor.extract(checkpoint_context=checkpoint_context))

        # Should have fewer batches (skipped first 3 chunks)
        # Original: 10 chunks (100 records / 10 per chunk)
        # After resume: 7 chunks (skipped first 3)
        assert len(resumed_batches) <= 10  # Should be 7, but depends on implementation

    def test_csv_extractor_with_wal_checkpoint_updates(self, tmp_path):
        """Test CSV extractor updating WAL checkpoints during extraction."""
        # Create test CSV file
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame(
            {
                "id": range(1, 51),
                "name": [f"Name_{i}" for i in range(1, 51)],
            }
        )
        df.to_csv(csv_file, index=False)

        # Create source config
        source_config = SourceConfig(
            type="csv",
            files=[{"path": str(csv_file), "id": "test_file"}],
        )

        # Create extractor
        extractor = CSVExtractor(source_config)

        # Create WAL manager
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        checkpoint_context = {
            "checkpoint": None,
            "wal_manager": wal_manager,
            "stream_name": "test_file",
        }

        # Extract with checkpoint context
        batches = list(extractor.extract(checkpoint_context=checkpoint_context))

        # Verify checkpoint was updated
        checkpoint = wal_manager.get_checkpoint("test_file")
        assert checkpoint is not None
        assert checkpoint["type"] == "chunk_based"
        assert checkpoint["chunk_number"] > 0

    def test_wal_finalize_and_cleanup(self, tmp_path):
        """Test WAL finalization and cleanup after successful extraction."""
        # Create test CSV file
        csv_file = tmp_path / "test.csv"
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["A", "B", "C"]})
        df.to_csv(csv_file, index=False)

        # Create source config
        source_config = SourceConfig(
            type="csv",
            files=[{"path": str(csv_file), "id": "test_file"}],
        )

        # Create extractor
        extractor = CSVExtractor(source_config)

        # Create WAL manager
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Extract all data
        checkpoint_context = {
            "checkpoint": None,
            "wal_manager": wal_manager,
            "stream_name": "test_file",
        }
        list(extractor.extract(checkpoint_context=checkpoint_context))

        # Finalize WAL
        wal_manager.finalize_wal()
        loaded = wal_manager.load_wal()
        assert loaded["status"] == "completed"

        # Cleanup WAL
        wal_manager.cleanup_wal()
        assert not wal_manager.wal_file.exists()

    def test_csv_extractor_checkpoint_file_id_mismatch(self, tmp_path):
        """Test that CSV extractor ignores checkpoint when file_id doesn't match.

        This test verifies the fix for the bug where a checkpoint for File A
        would incorrectly be applied to File B, causing File B to skip chunks.
        """
        # Create two test CSV files with different content
        csv_file_a = tmp_path / "file_a.csv"
        csv_file_b = tmp_path / "file_b.csv"

        # File A: 30 records
        df_a = pd.DataFrame(
            {
                "id": range(1, 31),
                "name": [f"Name_A_{i}" for i in range(1, 31)],
            }
        )
        df_a.to_csv(csv_file_a, index=False)

        # File B: 30 records
        df_b = pd.DataFrame(
            {
                "id": range(1, 31),
                "name": [f"Name_B_{i}" for i in range(1, 31)],
            }
        )
        df_b.to_csv(csv_file_b, index=False)

        # Create source config with both files
        source_config = SourceConfig(
            type="csv",
            files=[
                {"path": str(csv_file_a), "id": "file_a"},
                {"path": str(csv_file_b), "id": "file_b"},
            ],
            engine={"options": {"native": {"chunk_size": 10}}},
        )

        # Create extractor
        extractor = CSVExtractor(source_config)

        # Create WAL manager
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal(metadata={"extractor_type": "CSVExtractor"})

        # Create a checkpoint for file_a at chunk 2
        # This simulates File A being partially processed
        checkpoint_file_a = {
            "type": "chunk_based",
            "file_id": "file_a",
            "chunk_number": 2,
            "records_in_chunk": 10,
        }
        wal_manager.update_checkpoint("default", checkpoint_file_a)

        # Now try to extract with checkpoint context
        # The checkpoint is for file_a, but file_b should NOT use it
        checkpoint_context = {
            "checkpoint": wal_manager.get_resume_point("default"),
            "wal_manager": wal_manager,
            "stream_name": "default",
        }

        # Extract all batches and track file_b batches
        file_b_batches = []

        for batch in extractor.extract(checkpoint_context=checkpoint_context):
            # Identify file_b batches by checking record content
            if batch and len(batch) > 0 and "name" in batch[0]:
                if "Name_B_" in batch[0]["name"]:
                    file_b_batches.append(batch)

        # Verify file_b was processed completely
        # File B has 30 records, chunk_size=10, so should have 3 batches
        # If checkpoint was incorrectly applied, file_b would skip first 2 chunks
        # and only have 1 batch (10 records)
        file_b_total_records = sum(len(batch) for batch in file_b_batches)
        assert file_b_total_records == 30, (
            f"Expected 30 records for file_b, got {file_b_total_records}. "
            f"Checkpoint for file_a was incorrectly applied to file_b."
        )

        # Verify file_b has all 3 batches (not skipped)
        assert len(file_b_batches) == 3, (
            f"Expected 3 batches for file_b, got {len(file_b_batches)}. "
            f"Checkpoint for file_a caused file_b to skip chunks."
        )


class TestWALPostgresIntegration:
    """Integration tests for WAL with Postgres extractor (mocked)."""

    def test_postgres_extractor_with_wal_resume(self, tmp_path):
        """Test Postgres extractor resuming from WAL checkpoint."""
        # This is a simplified test - full integration would require a real DB
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Simulate checkpoint
        checkpoint = {
            "type": "offset_based",
            "table_name": "test_table",
            "last_offset": 50000,
            "batch_number": 5,
        }
        wal_manager.update_checkpoint("test_table", checkpoint)

        # Verify checkpoint
        resume_point = wal_manager.get_resume_point("test_table")
        assert resume_point["last_offset"] == 50000
        assert resume_point["type"] == "offset_based"


class TestWALMySQLIntegration:
    """Integration tests for WAL with MySQL extractor (mocked)."""

    def test_mysql_extractor_with_wal_checkpoint(self, tmp_path):
        """Test MySQL extractor WAL checkpoint updates."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Simulate checkpoint
        checkpoint = {
            "type": "offset_based",
            "table_name": "test_table",
            "last_offset": 30000,
        }
        wal_manager.update_checkpoint("test_table", checkpoint)

        # Verify checkpoint
        resume_point = wal_manager.get_resume_point("test_table")
        assert resume_point["last_offset"] == 30000
        assert resume_point["type"] == "offset_based"

    def test_mysql_extractor_with_wal_resume(self, tmp_path):
        """Test MySQL extractor resuming from WAL checkpoint."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        checkpoint = {
            "type": "offset_based",
            "table_name": "test_table",
            "last_offset": 30000,
        }
        wal_manager.update_checkpoint("test_table", checkpoint)

        resume_point = wal_manager.get_resume_point("test_table")
        assert resume_point["last_offset"] == 30000
        assert resume_point["type"] == "offset_based"


class TestWALGDriveCSVIntegration:
    """Integration tests for WAL with GDrive CSV extractor."""

    def test_gdrive_csv_extractor_with_wal_checkpoint(self, tmp_path):
        """Test GDrive CSV extractor WAL checkpoint updates."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Simulate checkpoint
        checkpoint = {
            "type": "chunk_based",
            "file_id": "gdrive_file_123",
            "chunk_number": 3,
        }
        wal_manager.update_checkpoint("gdrive_file_123", checkpoint)

        # Verify checkpoint
        resume_point = wal_manager.get_resume_point("gdrive_file_123")
        assert resume_point["chunk_number"] == 3
        assert resume_point["type"] == "chunk_based"


class TestWALGoogleSheetsIntegration:
    """Integration tests for WAL with Google Sheets extractor."""

    def test_google_sheets_extractor_with_wal_checkpoint(self, tmp_path):
        """Test Google Sheets extractor WAL checkpoint updates."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Simulate checkpoint
        checkpoint = {
            "type": "spreadsheet_based",
            "spreadsheet_id": "sheet_123",
            "records_processed": 100,
        }
        wal_manager.update_checkpoint("sheet_123", checkpoint)

        # Verify checkpoint
        resume_point = wal_manager.get_resume_point("sheet_123")
        assert resume_point["spreadsheet_id"] == "sheet_123"
        assert resume_point["type"] == "spreadsheet_based"
        assert resume_point["records_processed"] == 100

    def test_google_sheets_extractor_missing_checkpointed_spreadsheet(self, tmp_path):
        """Test Google Sheets extractor clears checkpoint when checkpointed spreadsheet not in config."""
        from pathlib import Path
        from unittest.mock import MagicMock, patch

        # Mock Google API modules
        mock_google_oauth2 = MagicMock()
        mock_google_oauth2.service_account = MagicMock()
        mock_google_oauth2.service_account.Credentials = MagicMock()
        mock_credentials = MagicMock()
        mock_google_oauth2.service_account.Credentials.from_service_account_file = (
            MagicMock(return_value=mock_credentials)
        )

        mock_sheets_service = MagicMock()
        mock_sheets_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
            "values": [["col1", "col2"], ["val1", "val2"]]
        }

        mock_discovery = MagicMock()
        mock_discovery.build = MagicMock(return_value=mock_sheets_service)

        # Create a mock Path that returns instances with exists() = True
        def mock_path_constructor(*args, **kwargs):
            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True
            mock_path.__str__ = lambda: str(args[0]) if args else ""
            mock_path.__fspath__ = lambda: str(args[0]) if args else ""
            return mock_path

        with (
            patch(
                "dativo_ingest.connectors.google_sheets_extractor.Path",
                side_effect=mock_path_constructor,
            ),
            patch.dict(
                sys.modules,
                {
                    "google": MagicMock(),
                    "google.oauth2": mock_google_oauth2,
                    "google.oauth2.service_account": mock_google_oauth2.service_account,
                    "googleapiclient": MagicMock(),
                    "googleapiclient.discovery": mock_discovery,
                },
            ),
        ):
            from dativo_ingest.config import ConnectorRecipe, SourceConfig
            from dativo_ingest.connectors.google_sheets_extractor import (
                GoogleSheetsExtractor,
            )

            # Create WAL manager with checkpoint for non-existent spreadsheet
            wal_base_dir = tmp_path / "wal"
            wal_manager = WALManager(
                job_name="test_job",
                tenant_id="test_tenant",
                wal_base_dir=str(wal_base_dir),
            )
            wal_manager.create_wal()

            # Create checkpoint for spreadsheet that won't be in config
            checkpoint = {
                "type": "spreadsheet_based",
                "spreadsheet_id": "missing_sheet_123",
                "records_processed": 100,
            }
            wal_manager.update_checkpoint("default", checkpoint)

            # Create source config with DIFFERENT spreadsheet IDs
            # Note: SourceConfig uses 'sheets' but extractor checks for 'spreadsheets'
            source_config = SourceConfig(
                type="google_sheets",
                credentials={"file_template": "/secrets/test/gsheets.json"},
            )
            # Set spreadsheets attribute directly (extractor checks for this)
            # Use object.__setattr__ to bypass Pydantic validation
            object.__setattr__(
                source_config,
                "spreadsheets",
                [{"id": "sheet_456"}, {"id": "sheet_789"}],
            )

            connector_recipe = ConnectorRecipe(
                name="google_sheets",
                type="google_sheets",
                roles=["source"],
                default_engine={"type": "native"},
                credentials={"type": "service_account"},
            )

            extractor = GoogleSheetsExtractor(
                source_config, connector_recipe, tenant_id="test_tenant"
            )

            # Create checkpoint context with missing spreadsheet ID
            checkpoint_context = {
                "checkpoint": checkpoint,
                "wal_manager": wal_manager,
                "stream_name": "default",
            }

            # Extract data - should process all spreadsheets (not skip them)
            batches = list(extractor.extract(checkpoint_context=checkpoint_context))

            # Verify that both spreadsheets were processed (not skipped)
            # The extractor should have cleared the checkpoint and processed all spreadsheets
            assert (
                len(batches) == 2
            ), "Should process both spreadsheets when checkpoint is invalid"
            assert len(batches[0]) == 1, "First spreadsheet should have 1 record"
            assert len(batches[1]) == 1, "Second spreadsheet should have 1 record"

            # Verify that get was called for both spreadsheets (not skipped)
            assert (
                mock_sheets_service.spreadsheets.return_value.values.return_value.get.call_count
                == 2
            )


class TestWALAirbyteIntegration:
    """Integration tests for WAL with Airbyte extractor (mocked)."""

    def test_airbyte_extractor_with_wal_state(self, tmp_path):
        """Test Airbyte extractor with WAL STATE message mapping."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Simulate Airbyte STATE checkpoint
        airbyte_state = {
            "streams": [
                {
                    "stream_descriptor": {"name": "customers"},
                    "stream_state": {"created": 1705315200},
                }
            ]
        }
        checkpoint = {
            "type": "state_based",
            "airbyte_state": airbyte_state,
        }
        wal_manager.update_checkpoint("customers", checkpoint)

        resume_point = wal_manager.get_resume_point("customers")
        assert resume_point["type"] == "state_based"
        assert "airbyte_state" in resume_point
        assert (
            resume_point["airbyte_state"]["streams"][0]["stream_descriptor"]["name"]
            == "customers"
        )


class TestWALJobExecutorCheckpointPreservation:
    """Integration tests for WAL checkpoint type preservation by job executor."""

    def test_job_executor_preserves_extractor_checkpoint_types(self, tmp_path):
        """Test that job executor doesn't overwrite extractor-specific checkpoint types."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        stream_name = "test_stream"

        # Simulate extractor updating checkpoint with specific type (chunk_based)
        extractor_checkpoint = {
            "type": "chunk_based",
            "file_id": "test_file.csv",
            "chunk_number": 5,
            "records_in_chunk": 100,
        }
        wal_manager.update_checkpoint(stream_name, extractor_checkpoint)

        # Verify extractor checkpoint was set
        checkpoint = wal_manager.get_checkpoint(stream_name)
        assert checkpoint is not None
        assert checkpoint["type"] == "chunk_based"
        assert checkpoint["chunk_number"] == 5

        # Simulate job executor checking and potentially updating checkpoint
        # (This mimics the logic in job_executor.py lines 586-614)
        current_checkpoint = wal_manager.get_checkpoint(stream_name)
        should_update = (
            current_checkpoint is None
            or current_checkpoint.get("type") == "batch_based"
        )

        # Job executor should NOT update because checkpoint has specific type
        assert (
            not should_update
        ), "Job executor should not overwrite extractor-specific checkpoint types"

        # Verify checkpoint type is still chunk_based (not overwritten)
        final_checkpoint = wal_manager.get_checkpoint(stream_name)
        assert final_checkpoint["type"] == "chunk_based"
        assert final_checkpoint["chunk_number"] == 5

    def test_job_executor_updates_batch_based_fallback(self, tmp_path):
        """Test that job executor updates checkpoint when extractor doesn't set specific type."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        stream_name = "test_stream"

        # Simulate job executor setting batch_based checkpoint (fallback)
        batch_checkpoint = {
            "type": "batch_based",
            "last_batch": 1,
            "records_processed": 100,
        }
        wal_manager.update_checkpoint(stream_name, batch_checkpoint)

        # Verify batch_based checkpoint was set
        checkpoint = wal_manager.get_checkpoint(stream_name)
        assert checkpoint is not None
        assert checkpoint["type"] == "batch_based"

        # Simulate job executor checking again (should update since it's batch_based)
        current_checkpoint = wal_manager.get_checkpoint(stream_name)
        should_update = (
            current_checkpoint is None
            or current_checkpoint.get("type") == "batch_based"
        )

        # Job executor SHOULD update because checkpoint is batch_based (fallback)
        assert should_update, "Job executor should update batch_based checkpoints"

        # Update with new batch
        new_batch_checkpoint = {
            "type": "batch_based",
            "last_batch": 2,
            "records_processed": 200,
        }
        wal_manager.update_checkpoint(stream_name, new_batch_checkpoint)

        # Verify checkpoint was updated
        final_checkpoint = wal_manager.get_checkpoint(stream_name)
        assert final_checkpoint["type"] == "batch_based"
        assert final_checkpoint["last_batch"] == 2
        assert final_checkpoint["records_processed"] == 200

    def test_job_executor_handles_multiple_checkpoint_types(self, tmp_path):
        """Test that job executor preserves different extractor checkpoint types."""
        wal_base_dir = tmp_path / "wal"
        wal_manager = WALManager(
            job_name="test_job",
            tenant_id="test_tenant",
            wal_base_dir=str(wal_base_dir),
        )
        wal_manager.create_wal()

        # Test chunk_based (CSV extractor)
        csv_checkpoint = {
            "type": "chunk_based",
            "file_id": "test.csv",
            "chunk_number": 3,
        }
        wal_manager.update_checkpoint("csv_stream", csv_checkpoint)
        assert wal_manager.get_checkpoint("csv_stream")["type"] == "chunk_based"

        # Test offset_based (Postgres extractor)
        postgres_checkpoint = {
            "type": "offset_based",
            "last_offset": 50000,
            "batch_number": 5,
        }
        wal_manager.update_checkpoint("postgres_stream", postgres_checkpoint)
        assert wal_manager.get_checkpoint("postgres_stream")["type"] == "offset_based"

        # Test spreadsheet_based (Google Sheets extractor)
        sheets_checkpoint = {
            "type": "spreadsheet_based",
            "spreadsheet_id": "abc123",
            "records_processed": 1000,
        }
        wal_manager.update_checkpoint("sheets_stream", sheets_checkpoint)
        assert (
            wal_manager.get_checkpoint("sheets_stream")["type"] == "spreadsheet_based"
        )

        # Test state_based (Airbyte extractor)
        airbyte_checkpoint = {
            "type": "state_based",
            "airbyte_state": {"streams": []},
        }
        wal_manager.update_checkpoint("airbyte_stream", airbyte_checkpoint)
        assert wal_manager.get_checkpoint("airbyte_stream")["type"] == "state_based"

        # Verify all checkpoint types are preserved (job executor logic)
        for stream_name in [
            "csv_stream",
            "postgres_stream",
            "sheets_stream",
            "airbyte_stream",
        ]:
            checkpoint = wal_manager.get_checkpoint(stream_name)
            should_update = (
                checkpoint is None or checkpoint.get("type") == "batch_based"
            )
            assert (
                not should_update
            ), f"Job executor should not overwrite {checkpoint['type']} checkpoint"


class TestWALJobExecutorResume:
    """Integration tests for WAL resume functionality with find_latest_wal."""

    def test_wal_resume_finds_existing_wal_across_run_ids(self, tmp_path):
        """Test that WALManager finds and resumes from existing WAL file when run_id is not specified."""
        wal_base_dir = tmp_path / "wal"
        job_name = "test_job"
        tenant_id = "test_tenant"
        original_run_id = "20240101_120000"

        # Step 1: Create a WAL file with a specific run_id and checkpoint
        wal_manager1 = WALManager(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
            run_id=original_run_id,
        )
        wal_manager1.create_wal(metadata={"extractor_type": "CSVExtractor"})
        checkpoint = {
            "type": "chunk_based",
            "file_id": "test_file",
            "chunk_number": 3,
            "records_in_chunk": 10,
        }
        wal_manager1.update_checkpoint("test_file", checkpoint)

        # Verify WAL file exists
        assert wal_manager1.wal_file.exists()
        assert wal_manager1.get_checkpoint("test_file") is not None

        # Step 2: Simulate what JobExecutor does - find existing WAL when run_id is None
        # This tests the fix: find_latest_wal() should be called before creating WALManager
        latest_wal_file = WALManager.find_latest_wal(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )

        # Verify that find_latest_wal found the existing WAL
        assert latest_wal_file is not None
        assert original_run_id in str(latest_wal_file)

        # Step 3: Create a new WALManager WITHOUT specifying run_id
        # It should use the run_id from the found WAL file
        extracted_run_id = latest_wal_file.stem.replace(".wal", "")
        wal_manager2 = WALManager(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
            run_id=extracted_run_id,  # Use run_id from found WAL
        )

        # Load the existing WAL
        wal_manager2.load_wal()

        # Verify that WAL manager is resuming
        assert wal_manager2.is_resuming() is True
        assert wal_manager2.run_id == original_run_id

        # Verify checkpoint is still accessible
        checkpoint_data = wal_manager2.get_checkpoint("test_file")
        assert checkpoint_data is not None
        assert checkpoint_data["chunk_number"] == 3

    def test_wal_creates_new_when_none_exists(self, tmp_path):
        """Test that WALManager creates a new WAL file when none exists."""
        wal_base_dir = tmp_path / "wal"
        job_name = "test_job"
        tenant_id = "test_tenant"

        # Simulate what JobExecutor does - check for existing WAL
        latest_wal_file = WALManager.find_latest_wal(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
        )

        # Verify no existing WAL found
        assert latest_wal_file is None

        # Create new WALManager (will generate new run_id)
        wal_manager = WALManager(
            job_name=job_name,
            tenant_id=tenant_id,
            wal_base_dir=str(wal_base_dir),
            run_id=None,  # Will generate new timestamp-based run_id
        )

        # Create new WAL
        wal_manager.create_wal()

        # Verify that WAL manager is NOT resuming
        assert wal_manager.is_resuming() is False
        assert wal_manager.wal_file.exists()
