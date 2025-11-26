"""Tag derivation for source metadata → Iceberg table properties.

This module collects explicitly defined tags from source systems, asset definitions,
and job configurations, then propagates them to Iceberg table properties.

NO AUTOMATIC CLASSIFICATION: All tags must be explicitly defined.

TAG HIERARCHY (later overrides earlier):
1. Source system tags (from connector metadata) - LOWEST PRIORITY
2. Asset definition tags (schema, compliance, finops) - MEDIUM PRIORITY
3. Job configuration tags (classification_overrides, finops, governance_overrides) - HIGHEST PRIORITY

Example:
- Source system says: email is "PII"
- Asset definition says: email is "SENSITIVE_PII"
- Job config says: email is "HIGH_PII"
- Result: email → "HIGH_PII" (job config wins)
"""

import re
from typing import Any, Dict, List, Optional, Set


class TagDerivation:
    """Collects explicitly defined tags from asset definitions and source metadata.

    NO AUTOMATIC CLASSIFICATION: This class only uses tags that are explicitly
    defined in the asset definition or provided via overrides. It does NOT
    perform any automatic pattern matching or field name analysis.
    """

    def __init__(
        self,
        asset_definition: Any,
        classification_overrides: Optional[Dict[str, str]] = None,
        finops: Optional[Dict[str, Any]] = None,
        governance_overrides: Optional[Dict[str, Any]] = None,
        source_tags: Optional[Dict[str, str]] = None,
        infrastructure_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize tag derivation.

        Args:
            asset_definition: AssetDefinition instance
            classification_overrides: Field-level classification overrides
                e.g., {"email": "pii", "amount": "financial"}
            finops: FinOps metadata
                e.g., {"cost_center": "FIN-001", "business_tags": ["payments", "revenue"]}
            governance_overrides: Governance metadata overrides
                e.g., {"retention_days": 365, "owner": "finance-team@company.com"}
            source_tags: Source system tags (LOWEST priority)
                e.g., {"email": "PII"} from connector metadata
            infrastructure_tags: Infrastructure tags (HIGH priority)
                e.g., {"cost_center": "CC-123", "environment": "prod"}
        """
        self.asset_definition = asset_definition
        self.classification_overrides = classification_overrides or {}
        self.finops = finops or {}
        self.governance_overrides = governance_overrides or {}
        self.source_tags = source_tags or {}  # Source system tags
        self.infrastructure_tags = infrastructure_tags or {}  # Infrastructure tags

    def _classify_field(self, field_name: str, field_type: str) -> Optional[str]:
        """Classify a field - ONLY uses explicit classifications, no auto-detection.

        Args:
            field_name: Field name
            field_type: Field type

        Returns:
            Classification string or None (always None - no auto-detection)
        """
        # No automatic classification - only use explicit tags
        return None

    def derive_field_classifications(self) -> Dict[str, str]:
        """Derive field-level classifications with three-level hierarchy.

        Precedence (highest to lowest):
        1. Job config overrides (classification_overrides)
        2. Asset definition schema (field.classification)
        3. Source system tags (source_tags)

        NO automatic detection. Only uses explicitly defined tags.

        Returns:
            Dictionary mapping field names to classification strings
        """
        classifications = {}

        for field in self.asset_definition.schema:
            field_name = field["name"]

            # Level 3: Check source system tags (LOWEST priority)
            if field_name in self.source_tags:
                classifications[field_name] = self.source_tags[field_name].lower()

            # Level 2: Check asset definition schema (MEDIUM priority - overrides source)
            if "classification" in field:
                classifications[field_name] = field["classification"].lower()

            # Level 1: Check job config overrides (HIGHEST priority - overrides all)
            if field_name in self.classification_overrides:
                classifications[field_name] = self.classification_overrides[
                    field_name
                ].lower()

        return classifications

    def derive_default_classification(self) -> Optional[str]:
        """Derive default table-level classification - ONLY from explicit definitions.

        NO automatic detection. Only uses:
        1. Explicit classification from compliance section
        2. Override from job config

        Returns:
            Default classification string or None
        """
        # Check for override first
        if "default" in self.classification_overrides:
            return self.classification_overrides["default"].lower()

        # Check compliance section
        if self.asset_definition.compliance:
            if self.asset_definition.compliance.classification:
                # Take the first classification as default
                classifications = self.asset_definition.compliance.classification
                if classifications:
                    return classifications[0].lower()

        # NO automatic derivation from field classifications
        return None

    def derive_governance_tags(self) -> Dict[str, str]:
        """Derive governance tags.

        Returns:
            Dictionary of governance tags
        """
        tags = {}

        # Retention days
        retention_days = None
        if self.governance_overrides.get("retention_days") is not None:
            retention_days = self.governance_overrides["retention_days"]
        elif (
            self.asset_definition.compliance
            and self.asset_definition.compliance.retention_days is not None
        ):
            retention_days = self.asset_definition.compliance.retention_days

        if retention_days is not None:  # Allow 0 as valid value
            tags["retention_days"] = str(retention_days)

        # Owner
        owner = None
        if "owner" in self.governance_overrides:
            # Check if override is explicitly set (even if empty string)
            owner = self.governance_overrides["owner"]
            if owner:  # Only add if non-empty
                tags["owner"] = owner
        elif self.asset_definition.team and self.asset_definition.team.owner:
            owner = self.asset_definition.team.owner
            if owner:  # Only add if non-empty
                tags["owner"] = owner

        # Domain
        if self.asset_definition.domain:
            tags["domain"] = self.asset_definition.domain

        # Data product
        if (
            hasattr(self.asset_definition, "dataProduct")
            and self.asset_definition.dataProduct
        ):
            tags["data_product"] = self.asset_definition.dataProduct

        # Regulations (if any)
        if (
            self.asset_definition.compliance
            and self.asset_definition.compliance.regulations
        ):
            tags["regulations"] = ",".join(self.asset_definition.compliance.regulations)

        return tags

    def derive_finops_tags(self) -> Dict[str, str]:
        """Derive FinOps tags.

        Returns:
            Dictionary of FinOps tags
        """
        tags = {}

        # Get finops from overrides first, then merge with asset definition
        finops_data = self.finops.copy() if self.finops else {}

        # Merge with asset definition finops (asset values as base, overrides take precedence)
        if hasattr(self.asset_definition, "finops") and self.asset_definition.finops:
            # Convert FinOpsModel to dict if needed
            asset_finops = {}
            if hasattr(self.asset_definition.finops, "model_dump"):
                asset_finops = self.asset_definition.finops.model_dump()
            elif hasattr(self.asset_definition.finops, "dict"):
                # Fallback for older Pydantic versions
                asset_finops = self.asset_definition.finops.dict()
            else:
                # Try to access as dict-like
                asset_finops = {
                    "cost_center": getattr(
                        self.asset_definition.finops, "cost_center", None
                    ),
                    "business_tags": getattr(
                        self.asset_definition.finops, "business_tags", None
                    ),
                    "project": getattr(self.asset_definition.finops, "project", None),
                    "environment": getattr(
                        self.asset_definition.finops, "environment", None
                    ),
                }
                # Remove None values
                asset_finops = {k: v for k, v in asset_finops.items() if v is not None}

            # Merge: asset values as base, overrides take precedence
            finops_data = {**asset_finops, **finops_data}

        if not finops_data:
            return tags

        # Cost center
        if finops_data.get("cost_center"):
            tags["cost_center"] = str(finops_data["cost_center"])

        # Business tags
        if finops_data.get("business_tags"):
            business_tags = finops_data["business_tags"]
            if isinstance(business_tags, list):
                tags["business_tags"] = ",".join(business_tags)
            else:
                tags["business_tags"] = str(business_tags)

        # Project
        if finops_data.get("project"):
            tags["project"] = str(finops_data["project"])

        # Environment
        if finops_data.get("environment"):
            tags["environment"] = str(finops_data["environment"])

        return tags

    def derive_infrastructure_tags(self) -> Dict[str, str]:
        """Derive infrastructure tags.

        Infrastructure tags have HIGH priority and override finops/governance tags.

        Returns:
            Dictionary of infrastructure tags
        """
        tags = {}

        if not self.infrastructure_tags:
            return tags

        # Infrastructure tags are passed through directly with "infrastructure." namespace
        for key, value in self.infrastructure_tags.items():
            if isinstance(value, list):
                tags[key] = ",".join(value)
            else:
                tags[key] = str(value)

        return tags

    def derive_all_tags(self) -> Dict[str, str]:
        """Derive all tags for Iceberg table properties.

        Tag hierarchy (highest to lowest priority):
        1. Infrastructure tags - HIGHEST (overrides everything)
        2. Job config tags (classification_overrides, finops, governance_overrides)
        3. Asset definition tags
        4. Source system tags - LOWEST

        Returns:
            Dictionary of all tags in namespaced format:
            - classification.default
            - classification.fields.<field_name>
            - governance.*
            - finops.*
            - infrastructure.*
        """
        tags = {}

        # Classification tags
        default_classification = self.derive_default_classification()
        if default_classification:
            tags["classification.default"] = default_classification

        field_classifications = self.derive_field_classifications()
        for field_name, classification in field_classifications.items():
            tags[f"classification.fields.{field_name}"] = classification

        # Governance tags
        governance_tags = self.derive_governance_tags()
        for key, value in governance_tags.items():
            tags[f"governance.{key}"] = value

        # FinOps tags
        finops_tags = self.derive_finops_tags()
        for key, value in finops_tags.items():
            tags[f"finops.{key}"] = value

        # Infrastructure tags (HIGHEST priority - can override finops/governance)
        infrastructure_tags = self.derive_infrastructure_tags()
        for key, value in infrastructure_tags.items():
            # Infrastructure tags override finops/governance tags with same key
            infra_key = f"infrastructure.{key}"
            tags[infra_key] = value
            
            # Also override finops/governance if key matches
            if key in ["cost_center", "project", "environment"]:
                finops_key = f"finops.{key}"
                if finops_key in tags:
                    tags[finops_key] = value

        return tags


def derive_tags_from_asset(
    asset_definition: Any,
    classification_overrides: Optional[Dict[str, str]] = None,
    finops: Optional[Dict[str, Any]] = None,
    governance_overrides: Optional[Dict[str, Any]] = None,
    source_tags: Optional[Dict[str, str]] = None,
    infrastructure_tags: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Convenience function to derive all tags from asset definition.

    Args:
        asset_definition: AssetDefinition instance
        classification_overrides: Field-level classification overrides
        finops: FinOps metadata
        governance_overrides: Governance metadata overrides
        source_tags: Source system tags (LOWEST priority)
        infrastructure_tags: Infrastructure tags (HIGHEST priority)

    Returns:
        Dictionary of all namespaced tags
    """
    derivation = TagDerivation(
        asset_definition=asset_definition,
        classification_overrides=classification_overrides,
        finops=finops,
        governance_overrides=governance_overrides,
        source_tags=source_tags,
        infrastructure_tags=infrastructure_tags,
    )
    return derivation.derive_all_tags()
