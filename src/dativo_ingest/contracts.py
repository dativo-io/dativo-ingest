"""Data contract management with semantic versioning and validation."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .config import AssetDefinition
from .logging import get_logger


class ContractVersion:
    """Represents a versioned data contract."""

    def __init__(
        self,
        contract: AssetDefinition,
        version: str,
        author: str,
        timestamp: datetime,
        hash: str,
        change_type: str = "non-breaking",
    ):
        """Initialize contract version.

        Args:
            contract: Asset definition representing the contract
            version: Semantic version (MAJOR.MINOR.PATCH)
            author: Author of the contract version
            timestamp: Timestamp of the version
            hash: Hash of the contract content
            change_type: Type of change ('breaking' or 'non-breaking')
        """
        self.contract = contract
        self.version = version
        self.author = author
        self.timestamp = timestamp
        self.hash = hash
        self.change_type = change_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "version": self.version,
            "author": self.author,
            "timestamp": self.timestamp.isoformat(),
            "hash": self.hash,
            "change_type": self.change_type,
            "contract_id": self.contract.id,
            "contract_name": self.contract.name,
        }


class ContractManager:
    """Manages data contracts with versioning and validation."""

    def __init__(self, specs_dir: Optional[Path] = None):
        """Initialize contract manager.

        Args:
            specs_dir: Base directory for contract specs (default: /specs)
        """
        self.specs_dir = specs_dir or Path("/specs")
        self.logger = get_logger()

    def _compute_hash(self, contract_data: Dict[str, Any]) -> str:
        """Compute hash of contract content.

        Args:
            contract_data: Contract data dictionary

        Returns:
            SHA256 hash of the contract
        """
        # Exclude metadata fields from hash (version, author, timestamp)
        hashable_fields = {
            k: v
            for k, v in contract_data.items()
            if k not in ["version", "contractCreatedTs", "change_management"]
        }
        content = json.dumps(hashable_fields, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def _parse_version(self, version: str) -> Tuple[int, int, int]:
        """Parse semantic version string.

        Args:
            version: Version string (e.g., "1.2.3")

        Returns:
            Tuple of (major, minor, patch)

        Raises:
            ValueError: If version format is invalid
        """
        parts = version.split(".")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid version format: {version}. Expected MAJOR.MINOR.PATCH"
            )
        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError as e:
            raise ValueError(
                f"Invalid version format: {version}. Parts must be integers"
            ) from e

    def _increment_version(
        self, current_version: str, change_type: str
    ) -> str:
        """Increment version based on change type.

        Args:
            current_version: Current version string
            change_type: Change type ('breaking' or 'non-breaking')

        Returns:
            New version string
        """
        major, minor, patch = self._parse_version(current_version)
        
        if change_type == "breaking":
            # MAJOR version bump for breaking changes
            return f"{major + 1}.0.0"
        else:
            # MINOR version bump for non-breaking changes
            return f"{major}.{minor + 1}.0"

    def _detect_breaking_changes(
        self, old_contract: AssetDefinition, new_contract: AssetDefinition
    ) -> List[str]:
        """Detect breaking changes between contracts.

        Args:
            old_contract: Previous contract version
            new_contract: New contract version

        Returns:
            List of breaking change descriptions
        """
        breaking_changes = []

        # Build field maps
        old_fields = {f["name"]: f for f in old_contract.schema}
        new_fields = {f["name"]: f for f in new_contract.schema}

        # Check for removed required fields
        for field_name, field_def in old_fields.items():
            if field_def.get("required", False) and field_name not in new_fields:
                breaking_changes.append(
                    f"Required field '{field_name}' was removed"
                )

        # Check for type changes
        for field_name, old_field in old_fields.items():
            if field_name in new_fields:
                new_field = new_fields[field_name]
                old_type = old_field.get("type", "string")
                new_type = new_field.get("type", "string")
                if old_type != new_type:
                    breaking_changes.append(
                        f"Field '{field_name}' type changed from {old_type} to {new_type}"
                    )

        # Check for newly required fields
        for field_name, field_def in new_fields.items():
            if field_def.get("required", False):
                if field_name not in old_fields:
                    breaking_changes.append(
                        f"New required field '{field_name}' was added"
                    )
                elif not old_fields[field_name].get("required", False):
                    breaking_changes.append(
                        f"Field '{field_name}' changed from optional to required"
                    )

        return breaking_changes

    def get_contract_path(
        self, source_type: str, object_name: str, version: str
    ) -> Path:
        """Get path to contract file.

        Args:
            source_type: Source type (e.g., 'stripe', 'postgres')
            object_name: Object name (e.g., 'customers')
            version: Version string (e.g., '1.0')

        Returns:
            Path to contract file
        """
        # Parse version to get MAJOR.MINOR
        major, minor, _ = self._parse_version(version)
        version_dir = f"v{major}.{minor}"
        
        return (
            self.specs_dir
            / source_type
            / version_dir
            / f"{object_name}.yaml"
        )

    def save_contract(
        self,
        contract: AssetDefinition,
        author: str = "system",
        force: bool = False,
    ) -> ContractVersion:
        """Save contract with version control.

        Args:
            contract: Asset definition to save
            author: Author of the contract
            force: Force save even if validation fails

        Returns:
            ContractVersion instance

        Raises:
            ValueError: If contract validation fails or breaking changes detected
        """
        # Load contract data as dict for hashing
        contract_data = contract.model_dump(by_alias=True)
        contract_hash = self._compute_hash(contract_data)
        
        # Determine target path
        target_path = self.get_contract_path(
            contract.source_type, contract.object, contract.version
        )
        
        # Check if contract already exists
        existing_version = None
        if target_path.exists():
            existing_contract = AssetDefinition.from_yaml(target_path)
            existing_data = existing_contract.model_dump(by_alias=True)
            existing_hash = self._compute_hash(existing_data)
            
            # If content is identical, no need to save
            if existing_hash == contract_hash:
                self.logger.info(
                    f"Contract unchanged: {target_path}",
                    extra={"event_type": "contract_unchanged"},
                )
                return ContractVersion(
                    contract=contract,
                    version=contract.version,
                    author=author,
                    timestamp=datetime.now(timezone.utc),
                    hash=contract_hash,
                    change_type="none",
                )
            
            # Detect breaking changes
            breaking_changes = self._detect_breaking_changes(
                existing_contract, contract
            )
            
            if breaking_changes:
                change_type = "breaking"
                if not force:
                    raise ValueError(
                        f"Breaking changes detected:\n" +
                        "\n".join(f"  - {change}" for change in breaking_changes) +
                        "\nMust increment MAJOR version or use --force"
                    )
                self.logger.warning(
                    "Breaking changes detected",
                    extra={
                        "event_type": "contract_breaking_changes",
                        "changes": breaking_changes,
                    },
                )
            else:
                change_type = "non-breaking"
        else:
            change_type = "initial"
        
        # Create directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Add contract metadata
        contract_data["contractCreatedTs"] = datetime.now(timezone.utc).isoformat()
        
        # Add change management audit trail
        if not contract.change_management:
            contract_data["change_management"] = {}
        contract_data["change_management"]["version_history"] = True
        
        # Save contract
        with open(target_path, "w") as f:
            yaml.dump(contract_data, f, default_flow_style=False, sort_keys=False)
        
        self.logger.info(
            f"Contract saved: {target_path}",
            extra={
                "event_type": "contract_saved",
                "version": contract.version,
                "change_type": change_type,
                "hash": contract_hash,
            },
        )
        
        return ContractVersion(
            contract=contract,
            version=contract.version,
            author=author,
            timestamp=datetime.now(timezone.utc),
            hash=contract_hash,
            change_type=change_type,
        )

    def validate_contract(
        self, contract: AssetDefinition, strict: bool = True
    ) -> Tuple[bool, List[str]]:
        """Validate contract against ODCS v3.0.2 schema.

        Args:
            contract: Asset definition to validate
            strict: Whether to use strict validation

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []
        
        # Validate required ODCS fields
        if not contract.id:
            errors.append("Contract ID is required")
        if not contract.version:
            errors.append("Contract version is required")
        if not contract.status:
            errors.append("Contract status is required")
        if not contract.team or not contract.team.owner:
            errors.append("Contract owner is required")
        
        # Validate schema
        if not contract.schema or len(contract.schema) == 0:
            errors.append("Contract schema cannot be empty")
        
        # Validate schema fields
        for field in contract.schema:
            if "name" not in field:
                errors.append("Schema field missing 'name'")
            if "type" not in field:
                errors.append(f"Schema field '{field.get('name', 'unknown')}' missing 'type'")
        
        # Validate compliance if classification tags present
        if contract.compliance and contract.compliance.classification:
            for classification in contract.compliance.classification:
                if classification not in ["PII", "SENSITIVE", "PUBLIC", "INTERNAL", "CONFIDENTIAL"]:
                    if strict:
                        errors.append(
                            f"Invalid classification: {classification}. "
                            f"Expected: PII, SENSITIVE, PUBLIC, INTERNAL, or CONFIDENTIAL"
                        )
        
        # Validate retention policy
        if contract.compliance and contract.compliance.retention_days:
            if contract.compliance.retention_days < 0:
                errors.append("Retention days must be non-negative")
        
        # Validate version format
        try:
            self._parse_version(contract.version)
        except ValueError as e:
            errors.append(str(e))
        
        is_valid = len(errors) == 0
        
        if errors:
            self.logger.warning(
                "Contract validation failed",
                extra={
                    "event_type": "contract_validation_failed",
                    "errors": errors,
                },
            )
        
        return is_valid, errors

    def get_contract_history(
        self, source_type: str, object_name: str
    ) -> List[ContractVersion]:
        """Get version history for a contract.

        Args:
            source_type: Source type
            object_name: Object name

        Returns:
            List of ContractVersion instances in reverse chronological order
        """
        source_dir = self.specs_dir / source_type
        if not source_dir.exists():
            return []
        
        versions = []
        for version_dir in sorted(source_dir.iterdir(), reverse=True):
            if not version_dir.is_dir():
                continue
            
            contract_path = version_dir / f"{object_name}.yaml"
            if contract_path.exists():
                try:
                    contract = AssetDefinition.from_yaml(contract_path)
                    contract_data = contract.model_dump(by_alias=True)
                    contract_hash = self._compute_hash(contract_data)
                    
                    # Get timestamp from file metadata
                    timestamp = datetime.fromtimestamp(
                        contract_path.stat().st_mtime, tz=timezone.utc
                    )
                    
                    versions.append(
                        ContractVersion(
                            contract=contract,
                            version=contract.version,
                            author=contract.team.owner if contract.team else "unknown",
                            timestamp=timestamp,
                            hash=contract_hash,
                            change_type="unknown",
                        )
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to load contract: {contract_path}: {e}",
                        extra={"event_type": "contract_load_failed"},
                    )
        
        return versions

    def compare_contracts(
        self, old_version: str, new_version: str, source_type: str, object_name: str
    ) -> Dict[str, Any]:
        """Compare two contract versions.

        Args:
            old_version: Old version string
            new_version: New version string
            source_type: Source type
            object_name: Object name

        Returns:
            Comparison result dictionary
        """
        old_path = self.get_contract_path(source_type, object_name, old_version)
        new_path = self.get_contract_path(source_type, object_name, new_version)
        
        if not old_path.exists():
            raise ValueError(f"Old contract version not found: {old_path}")
        if not new_path.exists():
            raise ValueError(f"New contract version not found: {new_path}")
        
        old_contract = AssetDefinition.from_yaml(old_path)
        new_contract = AssetDefinition.from_yaml(new_path)
        
        breaking_changes = self._detect_breaking_changes(old_contract, new_contract)
        
        # Build field diffs
        old_fields = {f["name"]: f for f in old_contract.schema}
        new_fields = {f["name"]: f for f in new_contract.schema}
        
        added_fields = [
            name for name in new_fields if name not in old_fields
        ]
        removed_fields = [
            name for name in old_fields if name not in new_fields
        ]
        modified_fields = [
            name
            for name in old_fields
            if name in new_fields and old_fields[name] != new_fields[name]
        ]
        
        return {
            "old_version": old_version,
            "new_version": new_version,
            "breaking_changes": breaking_changes,
            "is_breaking": len(breaking_changes) > 0,
            "fields": {
                "added": added_fields,
                "removed": removed_fields,
                "modified": modified_fields,
            },
        }
