"""WAL (Write-Ahead Log) Manager for intra-run checkpointing.

The WAL Manager enables jobs to resume extraction within a single run
at page/offset/chunk boundaries, complementing incremental state which
tracks cross-run logical cursors.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .logging import get_logger


class WALManager:
    """Manages WAL files for intra-run checkpointing."""

    def __init__(
        self,
        job_name: str,
        tenant_id: Optional[str] = None,
        wal_base_dir: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        """Initialize WAL Manager.

        Args:
            job_name: Name of the job (used for WAL file naming)
            tenant_id: Optional tenant ID (used for directory structure)
            wal_base_dir: Base directory for WAL files (defaults to /app/wal)
            run_id: Optional run ID (defaults to timestamp-based)
        """
        self.job_name = job_name
        self.tenant_id = tenant_id or "default"
        self.wal_base_dir = Path(wal_base_dir) if wal_base_dir else Path("/app/wal")
        self.run_id = run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.logger = get_logger()

        # Build WAL directory path
        self.wal_dir = self.wal_base_dir / self.tenant_id / self.job_name
        self.wal_file = self.wal_dir / f"{self.run_id}.wal.json"

        # In-memory WAL state
        self._wal_data: Optional[Dict[str, Any]] = None
        self._is_resuming = False

    def create_wal(self, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new WAL file for this job run.

        Args:
            metadata: Optional metadata to include in WAL (extractor type, connector type, etc.)

        Returns:
            WAL data dictionary
        """
        # Check if WAL already exists (resume scenario)
        if self.wal_file.exists():
            self.logger.info(
                f"WAL file already exists, will resume: {self.wal_file}",
                extra={
                    "wal_file": str(self.wal_file),
                    "event_type": "wal_resume_detected",
                },
            )
            return self.load_wal()

        # Create WAL directory if needed
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # Initialize WAL data
        self._wal_data = {
            "version": "1.0",
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "run_id": self.run_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "status": "in_progress",
            "checkpoints": {},
            "metadata": metadata or {},
        }

        # Write initial WAL file
        self._write_wal()

        self.logger.info(
            f"Created WAL file: {self.wal_file}",
            extra={
                "wal_file": str(self.wal_file),
                "run_id": self.run_id,
                "event_type": "wal_created",
            },
        )

        return self._wal_data

    def load_wal(self) -> Dict[str, Any]:
        """Load existing WAL file (for resume scenario).

        Returns:
            WAL data dictionary

        Raises:
            FileNotFoundError: If WAL file doesn't exist
        """
        if not self.wal_file.exists():
            raise FileNotFoundError(f"WAL file not found: {self.wal_file}")

        try:
            with open(self.wal_file, "r") as f:
                self._wal_data = json.load(f)

            self._is_resuming = True

            self.logger.info(
                f"Loaded WAL file for resume: {self.wal_file}",
                extra={
                    "wal_file": str(self.wal_file),
                    "run_id": self.run_id,
                    "status": self._wal_data.get("status"),
                    "checkpoints": list(self._wal_data.get("checkpoints", {}).keys()),
                    "event_type": "wal_loaded",
                },
            )

            return self._wal_data
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Failed to load WAL file {self.wal_file}: {e}") from e

    def update_checkpoint(
        self,
        stream_name: str,
        checkpoint: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update checkpoint for a stream.

        Args:
            stream_name: Name of the stream/object being processed
            checkpoint: Checkpoint data (type-specific: page, offset, chunk, state)
            metadata: Optional additional metadata
        """
        if self._wal_data is None:
            raise RuntimeError("WAL not initialized. Call create_wal() first.")

        # Update checkpoint
        checkpoint_data = {
            **checkpoint,
            "last_checkpoint_time": datetime.utcnow().isoformat() + "Z",
        }
        if metadata:
            checkpoint_data["metadata"] = metadata

        self._wal_data["checkpoints"][stream_name] = checkpoint_data
        self._wal_data["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # Write to disk
        self._write_wal()

        self.logger.debug(
            f"Updated checkpoint for stream: {stream_name}",
            extra={
                "stream_name": stream_name,
                "checkpoint_type": checkpoint.get("type"),
                "event_type": "checkpoint_updated",
            },
        )

    def get_checkpoint(self, stream_name: str) -> Optional[Dict[str, Any]]:
        """Get checkpoint for a stream.

        Args:
            stream_name: Name of the stream/object

        Returns:
            Checkpoint data or None if not found
        """
        if self._wal_data is None:
            return None

        return self._wal_data.get("checkpoints", {}).get(stream_name)

    def get_resume_point(self, stream_name: str) -> Optional[Dict[str, Any]]:
        """Get resume point for a stream (alias for get_checkpoint for clarity).

        Args:
            stream_name: Name of the stream/object

        Returns:
            Checkpoint data for resuming, or None if starting fresh
        """
        checkpoint = self.get_checkpoint(stream_name)
        if checkpoint:
            self.logger.info(
                f"Resume point found for stream: {stream_name}",
                extra={
                    "stream_name": stream_name,
                    "checkpoint_type": checkpoint.get("type"),
                    "event_type": "resume_point_found",
                },
            )
        return checkpoint

    def finalize_wal(self) -> None:
        """Finalize WAL (mark as complete, ready for cleanup).

        This should be called after successful extraction and before
        Iceberg/Nessie commit.
        """
        if self._wal_data is None:
            return

        self._wal_data["status"] = "completed"
        self._wal_data["completed_at"] = datetime.utcnow().isoformat() + "Z"
        self._wal_data["updated_at"] = datetime.utcnow().isoformat() + "Z"

        # Write final state
        self._write_wal()

        self.logger.info(
            f"Finalized WAL: {self.wal_file}",
            extra={
                "wal_file": str(self.wal_file),
                "run_id": self.run_id,
                "event_type": "wal_finalized",
            },
        )

    def cleanup_wal(self) -> None:
        """Clean up WAL file (called after successful commit).

        Removes the WAL file and any associated temp files.
        """
        try:
            # Clean up temp file if it exists (orphaned from interrupted write)
            temp_file = self.wal_file.with_name(
                self.wal_file.name.replace(".wal.json", ".wal.json.tmp")
            )
            if temp_file.exists():
                try:
                    temp_file.unlink()
                    self.logger.debug(
                        f"Removed WAL temp file: {temp_file}",
                        extra={
                            "temp_file": str(temp_file),
                            "event_type": "wal_temp_cleaned",
                        },
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to cleanup WAL temp file {temp_file}: {e}",
                        extra={
                            "temp_file": str(temp_file),
                            "event_type": "wal_temp_cleanup_failed",
                        },
                    )

            # Clean up WAL file
            if self.wal_file.exists():
                self.wal_file.unlink()
                self.logger.debug(
                    f"Removed WAL file: {self.wal_file}",
                    extra={"wal_file": str(self.wal_file), "event_type": "wal_cleaned"},
                )

        except Exception as e:
            # Don't fail the job if cleanup fails
            self.logger.warning(
                f"Failed to cleanup WAL file {self.wal_file}: {e}",
                extra={
                    "wal_file": str(self.wal_file),
                    "event_type": "wal_cleanup_failed",
                },
            )

    def is_resuming(self) -> bool:
        """Check if this is a resume scenario.

        Returns:
            True if resuming from existing WAL, False if starting fresh
        """
        return self._is_resuming

    def _write_wal(self) -> None:
        """Write WAL data to disk."""
        if self._wal_data is None:
            return

        # Ensure directory exists
        self.wal_dir.mkdir(parents=True, exist_ok=True)

        # Write atomically (write to temp file, then rename)
        temp_file = self.wal_file.with_name(
            self.wal_file.name.replace(".wal.json", ".wal.json.tmp")
        )
        try:
            with open(temp_file, "w") as f:
                json.dump(self._wal_data, f, indent=2)
            temp_file.replace(self.wal_file)
        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                temp_file.unlink()
            raise RuntimeError(f"Failed to write WAL file {self.wal_file}: {e}") from e

    @staticmethod
    def find_latest_wal(
        job_name: str, tenant_id: str, wal_base_dir: Optional[str] = None
    ) -> Optional[Path]:
        """Find the latest WAL file for a job (for resume scenarios).

        Args:
            job_name: Name of the job
            tenant_id: Tenant ID
            wal_base_dir: Base directory for WAL files

        Returns:
            Path to latest WAL file or None if not found
        """
        base_dir = Path(wal_base_dir) if wal_base_dir else Path("/app/wal")
        wal_dir = base_dir / tenant_id / job_name

        if not wal_dir.exists():
            return None

        # Collect all non-finalized WALs and extract run_id from filename
        wal_files = []
        for p in wal_dir.glob("*.wal.json"):
            try:
                # Read status from JSON to check if finalized
                with open(p, "r") as f:
                    wal_data = json.load(f)
                status = wal_data.get("status", "in_progress")

                # Only include non-finalized WALs (status != "completed")
                if status != "completed":
                    # Extract run_id from filename (e.g., "20240101_120000.wal.json" -> "20240101_120000")
                    run_id = p.stem.replace(".wal", "")
                    wal_files.append((run_id, p))
            except (json.JSONDecodeError, IOError, KeyError):
                # Skip invalid or unreadable files
                continue

        if not wal_files:
            return None

        # Sort by run_id descending (newest first)
        # run_id format is YYYYMMDD_HHMMSS, so string sort works correctly
        wal_files.sort(key=lambda x: x[0], reverse=True)
        return wal_files[0][1]
