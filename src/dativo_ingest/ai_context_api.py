"""AI-readable context API for metadata access with policy enforcement."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import AssetDefinition
from .contracts import ContractManager
from .lineage import LineageTracker
from .logging import get_logger


class PolicyGuard:
    """Enforces access policies for AI metadata access."""

    def __init__(self, policy_config: Optional[Dict[str, Any]] = None):
        """Initialize policy guard.

        Args:
            policy_config: Policy configuration dictionary
        """
        self.policy_config = policy_config or {}
        self.logger = get_logger()

    def check_access(
        self,
        resource_type: str,
        resource_id: str,
        requester: str,
        classification: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Check if requester has access to resource.

        Args:
            resource_type: Type of resource (asset, lineage, metrics)
            resource_id: Resource identifier
            requester: Requester identifier (user, service, agent)
            classification: Data classification tags

        Returns:
            Tuple of (is_allowed, denial_reason)
        """
        # Check if requester is allowed
        allowed_requesters = self.policy_config.get("allowed_requesters", [])
        if allowed_requesters and requester not in allowed_requesters:
            return False, f"Requester '{requester}' not in allowed list"
        
        # Check classification-based restrictions
        if classification:
            restricted_classifications = self.policy_config.get(
                "restricted_classifications", ["PII", "SENSITIVE"]
            )
            for tag in classification:
                if tag in restricted_classifications:
                    # Check if requester has elevated access
                    elevated_requesters = self.policy_config.get(
                        "elevated_requesters", []
                    )
                    if requester not in elevated_requesters:
                        return False, f"Access denied: {tag} data requires elevated permissions"
        
        self.logger.debug(
            f"Policy check passed: {resource_type}/{resource_id}",
            extra={"event_type": "policy_check", "requester": requester},
        )
        
        return True, None


class AIContextAPI:
    """Provides AI-readable context API for metadata access."""

    def __init__(
        self,
        contract_manager: Optional[ContractManager] = None,
        lineage_tracker: Optional[LineageTracker] = None,
        policy_guard: Optional[PolicyGuard] = None,
    ):
        """Initialize AI context API.

        Args:
            contract_manager: Contract manager instance
            lineage_tracker: Lineage tracker instance
            policy_guard: Policy guard instance
        """
        self.contract_manager = contract_manager or ContractManager()
        self.lineage_tracker = lineage_tracker or LineageTracker()
        self.policy_guard = policy_guard or PolicyGuard()
        self.logger = get_logger()

    def get_asset_context(
        self,
        source_type: str,
        object_name: str,
        version: Optional[str] = None,
        requester: str = "unknown",
    ) -> Dict[str, Any]:
        """Get complete context for an asset.

        Args:
            source_type: Source type
            object_name: Object name
            version: Specific version (default: latest)
            requester: Requester identifier

        Returns:
            Asset context dictionary

        Raises:
            PermissionError: If access is denied
            ValueError: If asset not found
        """
        # Find contract
        if version:
            contract_path = self.contract_manager.get_contract_path(
                source_type, object_name, version
            )
        else:
            # Get latest version
            history = self.contract_manager.get_contract_history(
                source_type, object_name
            )
            if not history:
                raise ValueError(
                    f"No contract found for {source_type}/{object_name}"
                )
            contract_path = self.contract_manager.get_contract_path(
                source_type, object_name, history[0].version
            )
        
        if not contract_path.exists():
            raise ValueError(f"Contract not found: {contract_path}")
        
        # Load contract
        contract = AssetDefinition.from_yaml(contract_path)
        
        # Check access policy
        classification = (
            contract.compliance.classification
            if contract.compliance
            else None
        )
        is_allowed, denial_reason = self.policy_guard.check_access(
            "asset", contract.id or contract.name, requester, classification
        )
        
        if not is_allowed:
            self.logger.warning(
                f"Access denied: {denial_reason}",
                extra={
                    "event_type": "access_denied",
                    "requester": requester,
                    "resource": f"{source_type}/{object_name}",
                },
            )
            raise PermissionError(denial_reason)
        
        # Build context
        context = {
            "asset": {
                "id": contract.id,
                "name": contract.name,
                "version": contract.version,
                "status": contract.status,
                "source_type": contract.source_type,
                "object": contract.object,
            },
            "schema": {
                "fields": [
                    {
                        "name": field.get("name"),
                        "type": field.get("type"),
                        "required": field.get("required", False),
                        "description": field.get("description", ""),
                        "classification": field.get("classification"),
                    }
                    for field in contract.schema
                ],
                "field_count": len(contract.schema),
            },
            "governance": {
                "owner": contract.team.owner if contract.team else "unknown",
                "classification": (
                    contract.compliance.classification
                    if contract.compliance
                    else []
                ),
                "retention_days": (
                    contract.compliance.retention_days
                    if contract.compliance
                    else None
                ),
                "regulations": (
                    contract.compliance.regulations
                    if contract.compliance
                    else []
                ),
            },
            "description": {
                "purpose": (
                    contract.description.purpose
                    if contract.description
                    else None
                ),
                "usage": (
                    contract.description.usage
                    if contract.description
                    else None
                ),
                "limitations": (
                    contract.description.limitations
                    if contract.description
                    else None
                ),
            },
            "metadata": {
                "odcs_version": contract.apiVersion,
                "tags": contract.tags or [],
                "domain": contract.domain,
                "data_product": contract.dataProduct,
            },
            "accessed_at": datetime.now(timezone.utc).isoformat(),
            "accessed_by": requester,
        }
        
        # Add data quality info if available
        if contract.data_quality:
            context["data_quality"] = {
                "monitoring_enabled": (
                    contract.data_quality.monitoring.enabled
                    if contract.data_quality.monitoring
                    else False
                ),
                "oncall_rotation": (
                    contract.data_quality.monitoring.oncall_rotation
                    if contract.data_quality.monitoring
                    else None
                ),
                "expectations_count": (
                    len(contract.data_quality.expectations)
                    if contract.data_quality.expectations
                    else 0
                ),
            }
        
        self.logger.info(
            f"Asset context accessed: {source_type}/{object_name}",
            extra={
                "event_type": "context_accessed",
                "requester": requester,
                "asset": contract.name,
            },
        )
        
        return context

    def get_lineage_context(
        self,
        source_type: str,
        object_name: str,
        direction: str = "both",
        requester: str = "unknown",
    ) -> Dict[str, Any]:
        """Get lineage context for an asset.

        Args:
            source_type: Source type
            object_name: Object name
            direction: Lineage direction ('upstream', 'downstream', 'both')
            requester: Requester identifier

        Returns:
            Lineage context dictionary

        Raises:
            PermissionError: If access is denied
        """
        # Check access policy
        is_allowed, denial_reason = self.policy_guard.check_access(
            "lineage", f"{source_type}/{object_name}", requester
        )
        
        if not is_allowed:
            raise PermissionError(denial_reason)
        
        node_id = f"asset://{source_type}/{object_name}"
        
        context = {
            "node_id": node_id,
            "direction": direction,
        }
        
        if direction in ["upstream", "both"]:
            context["upstream"] = self.lineage_tracker.get_upstream_lineage(node_id)
        
        if direction in ["downstream", "both"]:
            context["downstream"] = self.lineage_tracker.get_downstream_lineage(node_id)
        
        self.logger.info(
            f"Lineage context accessed: {source_type}/{object_name}",
            extra={
                "event_type": "lineage_accessed",
                "requester": requester,
            },
        )
        
        return context

    def get_finops_context(
        self,
        tenant_id: str,
        time_range_hours: int = 24,
        requester: str = "unknown",
    ) -> Dict[str, Any]:
        """Get FinOps context for a tenant.

        Args:
            tenant_id: Tenant identifier
            time_range_hours: Time range in hours
            requester: Requester identifier

        Returns:
            FinOps context dictionary

        Raises:
            PermissionError: If access is denied
        """
        # Check access policy
        is_allowed, denial_reason = self.policy_guard.check_access(
            "finops", tenant_id, requester
        )
        
        if not is_allowed:
            raise PermissionError(denial_reason)
        
        # In a real implementation, this would query metrics storage
        # For now, return a placeholder structure
        context = {
            "tenant_id": tenant_id,
            "time_range_hours": time_range_hours,
            "cost_summary": {
                "total_cost_usd": 0.0,
                "compute_cost_usd": 0.0,
                "storage_cost_usd": 0.0,
                "network_cost_usd": 0.0,
            },
            "resource_usage": {
                "cpu_seconds": 0,
                "memory_gb_hours": 0.0,
                "data_bytes_ingested": 0,
                "data_bytes_stored": 0,
            },
            "anomalies": [],
            "accessed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        self.logger.info(
            f"FinOps context accessed: {tenant_id}",
            extra={
                "event_type": "finops_accessed",
                "requester": requester,
            },
        )
        
        return context

    def search_assets(
        self,
        query: Optional[str] = None,
        classification: Optional[List[str]] = None,
        owner: Optional[str] = None,
        tags: Optional[List[str]] = None,
        requester: str = "unknown",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search for assets matching criteria.

        Args:
            query: Text search query
            classification: Filter by classification tags
            owner: Filter by owner
            tags: Filter by tags
            requester: Requester identifier
            limit: Maximum results to return

        Returns:
            List of matching asset summaries

        Raises:
            PermissionError: If access is denied
        """
        # Check access policy
        is_allowed, denial_reason = self.policy_guard.check_access(
            "search", "assets", requester
        )
        
        if not is_allowed:
            raise PermissionError(denial_reason)
        
        results = []
        
        # Scan specs directory for contracts
        specs_dir = self.contract_manager.specs_dir
        if not specs_dir.exists():
            return results
        
        for source_dir in specs_dir.iterdir():
            if not source_dir.is_dir():
                continue
            
            source_type = source_dir.name
            
            for version_dir in source_dir.iterdir():
                if not version_dir.is_dir():
                    continue
                
                for contract_file in version_dir.glob("*.yaml"):
                    try:
                        contract = AssetDefinition.from_yaml(contract_file)
                        
                        # Apply filters
                        if classification:
                            if not contract.compliance or not contract.compliance.classification:
                                continue
                            if not any(
                                c in contract.compliance.classification
                                for c in classification
                            ):
                                continue
                        
                        if owner:
                            if not contract.team or contract.team.owner != owner:
                                continue
                        
                        if tags:
                            if not contract.tags:
                                continue
                            if not any(t in contract.tags for t in tags):
                                continue
                        
                        if query:
                            # Simple text search in name and description
                            searchable = f"{contract.name} {contract.description.purpose if contract.description else ''}"
                            if query.lower() not in searchable.lower():
                                continue
                        
                        # Check access policy for this specific asset
                        asset_classification = (
                            contract.compliance.classification
                            if contract.compliance
                            else None
                        )
                        is_allowed, _ = self.policy_guard.check_access(
                            "asset",
                            contract.id or contract.name,
                            requester,
                            asset_classification,
                        )
                        
                        if not is_allowed:
                            continue
                        
                        results.append({
                            "id": contract.id,
                            "name": contract.name,
                            "version": contract.version,
                            "source_type": contract.source_type,
                            "object": contract.object,
                            "owner": contract.team.owner if contract.team else "unknown",
                            "classification": (
                                contract.compliance.classification
                                if contract.compliance
                                else []
                            ),
                            "tags": contract.tags or [],
                        })
                        
                        if len(results) >= limit:
                            break
                    
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to load contract: {contract_file}: {e}",
                            extra={"event_type": "search_error"},
                        )
                
                if len(results) >= limit:
                    break
            
            if len(results) >= limit:
                break
        
        self.logger.info(
            f"Asset search completed: {len(results)} results",
            extra={
                "event_type": "search_completed",
                "requester": requester,
                "results_count": len(results),
            },
        )
        
        return results
