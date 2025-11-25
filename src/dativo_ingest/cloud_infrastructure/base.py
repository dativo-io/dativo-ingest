"""Base classes for cloud infrastructure integration."""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import AssetDefinition, InfrastructureConfig, JobConfig

logger = logging.getLogger(__name__)


@dataclass
class InfrastructureContext:
    """Infrastructure context containing all metadata and configuration."""

    # Job identifiers
    tenant_id: str
    environment: str
    job_name: str

    # Infrastructure configuration
    provider: str
    platform: Optional[str] = None
    cluster_id: Optional[str] = None

    # Metadata
    tags: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    
    # Classification and governance
    classification_tags: Dict[str, str] = field(default_factory=dict)
    compliance_tags: Dict[str, str] = field(default_factory=dict)
    finops_tags: Dict[str, str] = field(default_factory=dict)
    
    # Resource identifiers
    compute_resources: Dict[str, Any] = field(default_factory=dict)
    storage_resources: Dict[str, Any] = field(default_factory=dict)
    network_resources: Dict[str, Any] = field(default_factory=dict)
    
    # Terraform configuration
    terraform_module_source: Optional[str] = None
    terraform_workspace: Optional[str] = None
    terraform_variables: Dict[str, Any] = field(default_factory=dict)


class TagPropagator:
    """Handles tag propagation and enrichment for cloud resources."""

    @staticmethod
    def derive_tags_from_job(job_config: JobConfig) -> Dict[str, str]:
        """Derive tags from job configuration.
        
        Args:
            job_config: Job configuration
            
        Returns:
            Dictionary of tags
        """
        tags = {}
        
        # Basic identifiers
        tags["TenantId"] = job_config.tenant_id
        if job_config.environment:
            tags["Environment"] = job_config.environment
        
        # Source and target information
        if job_config.source_connector:
            tags["SourceConnector"] = job_config.source_connector
        if job_config.target_connector:
            tags["TargetConnector"] = job_config.target_connector
        if job_config.asset:
            tags["Asset"] = job_config.asset
        
        return tags
    
    @staticmethod
    def derive_tags_from_asset(asset: AssetDefinition) -> Dict[str, str]:
        """Derive tags from asset definition.
        
        Args:
            asset: Asset definition
            
        Returns:
            Dictionary of tags
        """
        tags = {}
        
        # ODCS metadata
        if asset.domain:
            tags["Domain"] = asset.domain
        if asset.dataProduct:
            tags["DataProduct"] = asset.dataProduct
        if asset.status:
            tags["Status"] = asset.status
        
        # Asset tags
        if asset.tags:
            for tag in asset.tags:
                # Convert list tags to comma-separated string
                tags[f"AssetTag_{tag}"] = "true"
        
        # Team ownership
        if asset.team and asset.team.owner:
            tags["Owner"] = asset.team.owner
        
        return tags
    
    @staticmethod
    def derive_classification_tags(
        asset: AssetDefinition,
        classification_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Derive classification tags for data security and compliance.
        
        Args:
            asset: Asset definition
            classification_overrides: Optional classification overrides from job config
            
        Returns:
            Dictionary of classification tags
        """
        tags = {}
        
        # Compliance classifications
        if asset.compliance and asset.compliance.classification:
            classifications = asset.compliance.classification
            tags["DataClassification"] = ",".join(classifications)
            
            # Individual classification tags
            for classification in classifications:
                tags[f"Contains{classification}"] = "true"
        
        # Regulatory compliance
        if asset.compliance and asset.compliance.regulations:
            regulations = asset.compliance.regulations
            tags["Regulations"] = ",".join(regulations)
        
        # Retention policy
        if asset.compliance and asset.compliance.retention_days:
            tags["RetentionDays"] = str(asset.compliance.retention_days)
        
        # Encryption requirement
        if asset.compliance and asset.compliance.security:
            if asset.compliance.security.encryption_required:
                tags["EncryptionRequired"] = "true"
            if asset.compliance.security.access_control:
                tags["AccessControl"] = asset.compliance.security.access_control
        
        # Apply overrides
        if classification_overrides:
            # Default classification override
            if "default" in classification_overrides:
                tags["DataClassification"] = classification_overrides["default"]
        
        return tags
    
    @staticmethod
    def derive_finops_tags(
        job_config: JobConfig,
        asset: AssetDefinition
    ) -> Dict[str, str]:
        """Derive FinOps tags for cost allocation and tracking.
        
        Args:
            job_config: Job configuration
            asset: Asset definition
            
        Returns:
            Dictionary of FinOps tags
        """
        tags = {}
        
        # Job-level FinOps metadata
        if job_config.finops:
            if job_config.finops.get("cost_center"):
                tags["CostCenter"] = job_config.finops["cost_center"]
            if job_config.finops.get("project"):
                tags["Project"] = job_config.finops["project"]
            if job_config.finops.get("environment"):
                tags["FinOpsEnvironment"] = job_config.finops["environment"]
            if job_config.finops.get("business_tags"):
                business_tags = job_config.finops["business_tags"]
                tags["BusinessTags"] = ",".join(business_tags) if isinstance(business_tags, list) else str(business_tags)
        
        # Asset-level FinOps metadata
        if asset.finops:
            if asset.finops.cost_center and "CostCenter" not in tags:
                tags["CostCenter"] = asset.finops.cost_center
            if asset.finops.project and "Project" not in tags:
                tags["Project"] = asset.finops.project
        
        return tags
    
    @staticmethod
    def enrich_tags_with_infrastructure(
        base_tags: Dict[str, str],
        infrastructure_config: InfrastructureConfig
    ) -> Dict[str, str]:
        """Enrich tags with infrastructure-specific metadata.
        
        Args:
            base_tags: Base tags to enrich
            infrastructure_config: Infrastructure configuration
            
        Returns:
            Enriched tag dictionary
        """
        tags = base_tags.copy()
        
        # Provider information
        if infrastructure_config.provider:
            tags["InfraProvider"] = infrastructure_config.provider
        
        # Platform information
        if infrastructure_config.runtime and infrastructure_config.runtime.platform:
            tags["Platform"] = infrastructure_config.runtime.platform
        
        # Terraform metadata
        if infrastructure_config.terraform:
            if infrastructure_config.terraform.workspace:
                tags["TerraformWorkspace"] = infrastructure_config.terraform.workspace
            if infrastructure_config.terraform.module_version:
                tags["InfraVersion"] = infrastructure_config.terraform.module_version
        
        # Merge user-provided tags (these take precedence)
        if infrastructure_config.metadata and infrastructure_config.metadata.tags:
            tags.update(infrastructure_config.metadata.tags)
        
        # Add ManagedBy tag
        tags["ManagedBy"] = "dativo"
        
        return tags
    
    @staticmethod
    def build_complete_tag_set(
        job_config: JobConfig,
        asset: AssetDefinition
    ) -> Dict[str, str]:
        """Build complete tag set from all sources.
        
        Args:
            job_config: Job configuration
            asset: Asset definition
            
        Returns:
            Complete tag dictionary
        """
        tags = {}
        
        # 1. Base tags from job
        tags.update(TagPropagator.derive_tags_from_job(job_config))
        
        # 2. Asset metadata tags
        tags.update(TagPropagator.derive_tags_from_asset(asset))
        
        # 3. Classification and compliance tags
        tags.update(TagPropagator.derive_classification_tags(
            asset,
            job_config.classification_overrides
        ))
        
        # 4. FinOps tags
        tags.update(TagPropagator.derive_finops_tags(job_config, asset))
        
        # 5. Infrastructure enrichment
        if job_config.infrastructure:
            tags = TagPropagator.enrich_tags_with_infrastructure(
                tags,
                job_config.infrastructure
            )
        
        # 6. Timestamp
        import datetime
        tags["LastModified"] = datetime.datetime.utcnow().isoformat()
        
        return tags


class CloudInfrastructureManager(ABC):
    """Abstract base class for cloud infrastructure managers."""

    def __init__(
        self,
        job_config: JobConfig,
        asset: AssetDefinition,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize infrastructure manager.
        
        Args:
            job_config: Job configuration
            asset: Asset definition
            logger: Optional logger instance
        """
        self.job_config = job_config
        self.asset = asset
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        
        # Build infrastructure context
        self.context = self._build_context()
    
    def _build_context(self) -> InfrastructureContext:
        """Build infrastructure context from job and asset configuration.
        
        Returns:
            Infrastructure context
        """
        infra = self.job_config.infrastructure
        
        # Build complete tag set
        all_tags = TagPropagator.build_complete_tag_set(
            self.job_config,
            self.asset
        )
        
        # Extract different types of tags
        classification_tags = {k: v for k, v in all_tags.items() 
                             if k.startswith(("DataClassification", "Contains", "Regulations", "Retention"))}
        finops_tags = {k: v for k, v in all_tags.items() 
                      if k in ("CostCenter", "Project", "FinOpsEnvironment", "BusinessTags")}
        
        context = InfrastructureContext(
            tenant_id=self.job_config.tenant_id,
            environment=self.job_config.environment or "prod",
            job_name=self.job_config.asset or "unknown",
            provider=infra.provider if infra else "manual",
            tags=all_tags,
            classification_tags=classification_tags,
            finops_tags=finops_tags
        )
        
        # Add infrastructure-specific details
        if infra:
            context.labels = infra.metadata.labels if infra.metadata and infra.metadata.labels else {}
            context.annotations = infra.metadata.annotations if infra.metadata and infra.metadata.annotations else {}
            
            if infra.runtime:
                context.platform = infra.runtime.platform
                if infra.runtime.compute:
                    context.cluster_id = infra.runtime.compute.cluster_id
                    context.compute_resources = {
                        "instance_type": infra.runtime.compute.instance_type,
                        "instance_count": infra.runtime.compute.instance_count,
                        "auto_scaling": infra.runtime.compute.auto_scaling.model_dump() if infra.runtime.compute.auto_scaling else None
                    }
                if infra.runtime.storage:
                    context.storage_resources = infra.runtime.storage.model_dump()
                if infra.runtime.network:
                    context.network_resources = infra.runtime.network.model_dump()
            
            if infra.terraform:
                context.terraform_module_source = infra.terraform.module_source
                context.terraform_workspace = infra.terraform.workspace
                if infra.metadata and infra.metadata.variables:
                    context.terraform_variables = infra.metadata.variables
        
        return context
    
    @abstractmethod
    def validate_infrastructure(self) -> bool:
        """Validate infrastructure configuration and connectivity.
        
        Returns:
            True if infrastructure is valid and accessible
            
        Raises:
            ValueError: If infrastructure validation fails
        """
        pass
    
    @abstractmethod
    def apply_tags_to_resources(self, resource_ids: List[str]) -> Dict[str, bool]:
        """Apply tags to cloud resources.
        
        Args:
            resource_ids: List of resource identifiers to tag
            
        Returns:
            Dictionary mapping resource IDs to success status
        """
        pass
    
    @abstractmethod
    def get_terraform_variables(self) -> Dict[str, Any]:
        """Get Terraform variables from infrastructure configuration.
        
        Returns:
            Dictionary of Terraform variables
        """
        pass
    
    @abstractmethod
    def export_terraform_outputs(self, output_path: str) -> None:
        """Export Terraform outputs for downstream use.
        
        Args:
            output_path: Path to write Terraform outputs
        """
        pass
    
    def log_infrastructure_context(self) -> None:
        """Log infrastructure context for debugging and auditing."""
        self.logger.info(
            "Infrastructure context initialized",
            extra={
                "tenant_id": self.context.tenant_id,
                "environment": self.context.environment,
                "provider": self.context.provider,
                "platform": self.context.platform,
                "cluster_id": self.context.cluster_id,
                "tag_count": len(self.context.tags),
                "classification_tags": self.context.classification_tags,
                "finops_tags": self.context.finops_tags
            }
        )
