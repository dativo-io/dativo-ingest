"""Tag derivation for source metadata → Iceberg table properties.

This module collects explicitly defined tags from asset definitions and
source metadata, preparing them for propagation to Iceberg table properties.

NO AUTOMATIC CLASSIFICATION: All tags must be explicitly defined in:
- Asset definition schema (field.classification)
- Asset definition compliance section
- Asset definition finops section
- Job-level overrides
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
        """
        self.asset_definition = asset_definition
        self.classification_overrides = classification_overrides or {}
        self.finops = finops or {}
        self.governance_overrides = governance_overrides or {}

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
        """Derive field-level classifications - ONLY from explicit definitions.

        NO automatic detection. Only uses:
        1. Explicit classification in schema
        2. Classification overrides from job config

        Returns:
            Dictionary mapping field names to classification strings
        """
        classifications = {}

        for field in self.asset_definition.schema:
            field_name = field["name"]

            # Check for explicit classification in schema
            if "classification" in field:
                classifications[field_name] = field["classification"].lower()
                continue

            # Check for override from job config
            if field_name in self.classification_overrides:
                classifications[field_name] = self.classification_overrides[
                    field_name
                ].lower()
                continue

            # NO automatic classification - skip this field

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
        if self.governance_overrides.get("retention_days"):
            retention_days = self.governance_overrides["retention_days"]
        elif (
            self.asset_definition.compliance
            and self.asset_definition.compliance.retention_days
        ):
            retention_days = self.asset_definition.compliance.retention_days

        if retention_days:
            tags["retention_days"] = str(retention_days)

        # Owner
        owner = None
        if self.governance_overrides.get("owner"):
            owner = self.governance_overrides["owner"]
        elif self.asset_definition.team and self.asset_definition.team.owner:
            owner = self.asset_definition.team.owner

        if owner:
            tags["owner"] = owner

        # Domain
        if self.asset_definition.domain:
            tags["domain"] = self.asset_definition.domain

        # Data product
        if hasattr(self.asset_definition, "dataProduct") and self.asset_definition.dataProduct:
            tags["data_product"] = self.asset_definition.dataProduct

        # Regulations (if any)
        if (
            self.asset_definition.compliance
            and self.asset_definition.compliance.regulations
        ):
            tags["regulations"] = ",".join(
                self.asset_definition.compliance.regulations
            )

        return tags

    def derive_finops_tags(self) -> Dict[str, str]:
        """Derive FinOps tags.

        Returns:
            Dictionary of FinOps tags
        """
        tags = {}

        # Cost center
        if self.finops.get("cost_center"):
            tags["cost_center"] = str(self.finops["cost_center"])

        # Business tags
        if self.finops.get("business_tags"):
            business_tags = self.finops["business_tags"]
            if isinstance(business_tags, list):
                tags["business_tags"] = ",".join(business_tags)
            else:
                tags["business_tags"] = str(business_tags)

        # Project
        if self.finops.get("project"):
            tags["project"] = str(self.finops["project"])

        # Environment
        if self.finops.get("environment"):
            tags["environment"] = str(self.finops["environment"])

        return tags

    def derive_all_tags(self) -> Dict[str, str]:
        """Derive all tags for Iceberg table properties.

        Returns:
            Dictionary of all tags in namespaced format:
            - classification.default
            - classification.fields.<field_name>
            - governance.*
            - finops.*
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

        return tags


def derive_tags_from_asset(
    asset_definition: Any,
    classification_overrides: Optional[Dict[str, str]] = None,
    finops: Optional[Dict[str, Any]] = None,
    governance_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Convenience function to derive all tags from asset definition.

    Args:
        asset_definition: AssetDefinition instance
        classification_overrides: Field-level classification overrides
        finops: FinOps metadata
        governance_overrides: Governance metadata overrides

    Returns:
        Dictionary of all namespaced tags
    """
    derivation = TagDerivation(
        asset_definition=asset_definition,
        classification_overrides=classification_overrides,
        finops=finops,
        governance_overrides=governance_overrides,
    )
    return derivation.derive_all_tags()
