"""GCP infrastructure integration with comprehensive tag propagation."""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import CloudInfrastructureManager, InfrastructureContext

logger = logging.getLogger(__name__)


class GCPInfrastructureManager(CloudInfrastructureManager):
    """GCP-specific infrastructure manager with label propagation."""

    def __init__(self, job_config, asset, logger=None):
        """Initialize GCP infrastructure manager.
        
        Args:
            job_config: Job configuration
            asset: Asset definition
            logger: Optional logger instance
        """
        super().__init__(job_config, asset, logger)
        
        # Initialize GCP clients if google-cloud libraries are available
        self.gcp_available = False
        self.compute_client = None
        self.storage_client = None
        self.resource_manager_client = None
        
        try:
            from google.cloud import compute_v1, storage, resourcemanager_v3
            self.gcp_available = True
            
            # Initialize clients
            project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT"))
            if not project_id:
                self.logger.warning("GCP_PROJECT_ID not set - some operations may fail")
            
            self.compute_client = compute_v1.InstancesClient()
            self.storage_client = storage.Client(project=project_id)
            self.resource_manager_client = resourcemanager_v3.ProjectsClient()
            
            self.logger.info(f"GCP clients initialized for project: {project_id}")
        except ImportError:
            self.logger.warning("Google Cloud libraries not available - GCP API operations will be skipped")
    
    def _convert_tags_to_labels(self, tags: Dict[str, str]) -> Dict[str, str]:
        """Convert tags to GCP-compatible labels.
        
        GCP labels have restrictions:
        - Keys and values must be lowercase
        - Only hyphens, underscores, lowercase letters, and numbers allowed
        - Keys must start with a letter
        - Maximum 63 characters per key/value
        
        Args:
            tags: Tag dictionary
            
        Returns:
            Label dictionary compatible with GCP
        """
        labels = {}
        for key, value in tags.items():
            # Convert to lowercase and replace invalid characters
            label_key = key.lower().replace(" ", "_").replace(":", "_").replace("/", "_")
            label_value = str(value).lower().replace(" ", "_").replace(":", "_").replace("/", "_")
            
            # Ensure key starts with letter
            if not label_key[0].isalpha():
                label_key = f"tag_{label_key}"
            
            # Truncate if too long
            label_key = label_key[:63]
            label_value = label_value[:63]
            
            labels[label_key] = label_value
        
        return labels
    
    def validate_infrastructure(self) -> bool:
        """Validate GCP infrastructure configuration and connectivity.
        
        Returns:
            True if infrastructure is valid and accessible
            
        Raises:
            ValueError: If infrastructure validation fails
        """
        infra = self.job_config.infrastructure
        if not infra:
            self.logger.info("No infrastructure configuration - skipping validation")
            return True
        
        errors = []
        
        # Validate runtime platform
        if infra.runtime and infra.runtime.platform:
            platform = infra.runtime.platform
            valid_gcp_platforms = ["kubernetes", "gke", "dataproc", "cloud_run"]
            if platform not in valid_gcp_platforms:
                self.logger.warning(
                    f"Platform '{platform}' may not be GCP-specific. Valid GCP platforms: {valid_gcp_platforms}"
                )
        
        # Validate GKE cluster if specified
        if infra.runtime and infra.runtime.compute and infra.runtime.compute.cluster_id:
            cluster_id = os.path.expandvars(infra.runtime.compute.cluster_id)
            self.logger.info(f"Cluster ID specified: {cluster_id}")
            # Note: Actual validation would require GKE API client
        
        # Validate GCS bucket if specified
        if infra.runtime and infra.runtime.storage and infra.runtime.storage.bucket:
            bucket_name = os.path.expandvars(infra.runtime.storage.bucket)
            if self.gcp_available and self.storage_client:
                try:
                    bucket = self.storage_client.get_bucket(bucket_name)
                    self.logger.info(f"GCS bucket {bucket_name} validated successfully")
                except Exception as e:
                    errors.append(f"Failed to validate GCS bucket {bucket_name}: {e}")
            else:
                self.logger.info(f"Skipping GCS bucket validation for {bucket_name} (GCP libraries not available)")
        
        # Validate VPC and networking
        if infra.runtime and infra.runtime.network:
            network = infra.runtime.network
            if network.vpc_id:
                vpc_id = os.path.expandvars(network.vpc_id)
                self.logger.info(f"VPC specified: {vpc_id}")
                # Note: Actual validation would require Compute API client
        
        if errors:
            raise ValueError(f"GCP infrastructure validation failed: {'; '.join(errors)}")
        
        return True
    
    def apply_tags_to_resources(self, resource_ids: List[str]) -> Dict[str, bool]:
        """Apply labels to GCP resources.
        
        Args:
            resource_ids: List of GCP resource identifiers to label
            
        Returns:
            Dictionary mapping resource IDs to success status
        """
        if not self.gcp_available:
            self.logger.warning("GCP libraries not available - skipping label application")
            return {rid: False for rid in resource_ids}
        
        # Convert tags to GCP labels
        labels = self._convert_tags_to_labels(self.context.tags)
        
        results = {}
        for resource_id in resource_ids:
            try:
                # Label application depends on resource type
                # This is a placeholder for actual implementation
                self.logger.info(f"Would apply {len(labels)} labels to resource {resource_id}")
                results[resource_id] = True
            except Exception as e:
                self.logger.error(f"Failed to label resource {resource_id}: {e}")
                results[resource_id] = False
        
        return results
    
    def apply_labels_to_gcs_bucket(self, bucket_name: str) -> bool:
        """Apply labels to GCS bucket.
        
        Args:
            bucket_name: GCS bucket name
            
        Returns:
            True if successful
        """
        if not self.gcp_available or not self.storage_client:
            self.logger.warning("GCP libraries not available - skipping GCS bucket labeling")
            return False
        
        try:
            bucket_name = os.path.expandvars(bucket_name)
            bucket = self.storage_client.get_bucket(bucket_name)
            
            # Convert tags to labels
            labels = self._convert_tags_to_labels(self.context.tags)
            
            # Update bucket labels
            bucket.labels = labels
            bucket.patch()
            
            self.logger.info(f"Applied {len(labels)} labels to GCS bucket {bucket_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to label GCS bucket {bucket_name}: {e}")
            return False
    
    def apply_labels_to_gke_cluster(self, cluster_name: str, location: str) -> bool:
        """Apply labels to GKE cluster.
        
        Args:
            cluster_name: GKE cluster name
            location: GCP location (region or zone)
            
        Returns:
            True if successful
        """
        if not self.gcp_available:
            self.logger.warning("GCP libraries not available - skipping GKE cluster labeling")
            return False
        
        try:
            from google.cloud import container_v1
            
            cluster_name = os.path.expandvars(cluster_name)
            location = os.path.expandvars(location)
            project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT"))
            
            client = container_v1.ClusterManagerClient()
            
            # Get cluster
            cluster_path = f"projects/{project_id}/locations/{location}/clusters/{cluster_name}"
            cluster = client.get_cluster(name=cluster_path)
            
            # Convert tags to labels
            labels = self._convert_tags_to_labels(self.context.tags)
            
            # Update cluster with new labels
            update = container_v1.ClusterUpdate()
            update.desired_resource_labels = container_v1.ResourceLabels(labels=labels)
            
            operation = client.update_cluster(
                name=cluster_path,
                update=update
            )
            
            self.logger.info(f"Applied {len(labels)} labels to GKE cluster {cluster_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to label GKE cluster {cluster_name}: {e}")
            return False
    
    def apply_all_infrastructure_labels(self) -> Dict[str, bool]:
        """Apply labels to all infrastructure resources defined in configuration.
        
        Returns:
            Dictionary mapping resource types to success status
        """
        results = {}
        
        infra = self.job_config.infrastructure
        if not infra or not infra.runtime:
            self.logger.info("No infrastructure runtime configuration - skipping labeling")
            return results
        
        # Label GKE cluster if specified
        if infra.runtime.compute and infra.runtime.compute.cluster_id:
            cluster_id = infra.runtime.compute.cluster_id
            # Extract location from cluster ID or use default
            location = os.getenv("GCP_LOCATION", "us-central1")
            results["gke_cluster"] = self.apply_labels_to_gke_cluster(cluster_id, location)
        
        # Label GCS bucket if specified
        if infra.runtime.storage and infra.runtime.storage.bucket:
            bucket = infra.runtime.storage.bucket
            results["gcs_bucket"] = self.apply_labels_to_gcs_bucket(bucket)
        
        return results
    
    def get_terraform_variables(self) -> Dict[str, Any]:
        """Get Terraform variables for GCP infrastructure.
        
        Returns:
            Dictionary of Terraform variables
        """
        variables = {
            "tenant_id": self.context.tenant_id,
            "environment": self.context.environment,
            "gcp_project_id": os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT")),
            "gcp_region": os.getenv("GCP_REGION", "us-central1"),
        }
        
        # Add all labels (GCP equivalent of tags)
        variables["labels"] = self._convert_tags_to_labels(self.context.tags)
        variables["classification_labels"] = self._convert_tags_to_labels(self.context.classification_tags)
        variables["finops_labels"] = self._convert_tags_to_labels(self.context.finops_tags)
        
        # Add runtime configuration
        infra = self.job_config.infrastructure
        if infra:
            if infra.runtime:
                if infra.runtime.compute:
                    variables["machine_type"] = infra.runtime.compute.instance_type
                    variables["node_count"] = infra.runtime.compute.instance_count
                    if infra.runtime.compute.auto_scaling:
                        variables["enable_autoscaling"] = infra.runtime.compute.auto_scaling.enabled
                        variables["min_nodes"] = infra.runtime.compute.auto_scaling.min_instances
                        variables["max_nodes"] = infra.runtime.compute.auto_scaling.max_instances
                
                if infra.runtime.storage:
                    variables["gcs_bucket"] = infra.runtime.storage.bucket
                
                if infra.runtime.network:
                    variables["network"] = infra.runtime.network.vpc_id
                    variables["subnetwork_ids"] = infra.runtime.network.subnet_ids
                
                if infra.runtime.namespace:
                    variables["kubernetes_namespace"] = infra.runtime.namespace
                
                if infra.runtime.service_account:
                    variables["service_account"] = infra.runtime.service_account
            
            # Add Kubernetes labels and annotations
            if infra.metadata:
                if infra.metadata.labels:
                    variables["kubernetes_labels"] = infra.metadata.labels
                if infra.metadata.annotations:
                    variables["kubernetes_annotations"] = infra.metadata.annotations
                
                # Add user-provided variables (these override defaults)
                if infra.metadata.variables:
                    variables.update(infra.metadata.variables)
        
        return variables
    
    def export_terraform_outputs(self, output_path: str) -> None:
        """Export Terraform outputs for GCP infrastructure.
        
        Args:
            output_path: Path to write Terraform outputs
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        outputs = {
            "infrastructure_context": {
                "tenant_id": self.context.tenant_id,
                "environment": self.context.environment,
                "provider": "gcp",
                "platform": self.context.platform,
                "cluster_id": self.context.cluster_id
            },
            "labels": self._convert_tags_to_labels(self.context.tags),
            "classification_labels": self._convert_tags_to_labels(self.context.classification_tags),
            "finops_labels": self._convert_tags_to_labels(self.context.finops_tags),
            "kubernetes_labels": self.context.labels,
            "kubernetes_annotations": self.context.annotations,
            "terraform_variables": self.get_terraform_variables()
        }
        
        with open(output_path, "w") as f:
            json.dump(outputs, f, indent=2)
        
        self.logger.info(f"Exported Terraform outputs to {output_path}")
    
    def generate_terraform_tfvars(self, output_path: str) -> None:
        """Generate Terraform tfvars file for GCP infrastructure.
        
        Args:
            output_path: Path to write tfvars file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        variables = self.get_terraform_variables()
        
        # Convert to HCL format
        lines = []
        for key, value in variables.items():
            if isinstance(value, dict):
                lines.append(f'{key} = {{')
                for k, v in value.items():
                    if isinstance(v, str):
                        lines.append(f'  "{k}" = "{v}"')
                    else:
                        lines.append(f'  "{k}" = {json.dumps(v)}')
                lines.append('}')
            elif isinstance(value, list):
                lines.append(f'{key} = {json.dumps(value)}')
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f'{key} = {str(value).lower()}')
            elif value is None:
                lines.append(f'{key} = null')
            else:
                lines.append(f'{key} = {value}')
        
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        
        self.logger.info(f"Generated Terraform tfvars file: {output_path}")
    
    def run_terraform_apply(
        self,
        terraform_dir: str,
        auto_approve: bool = False
    ) -> subprocess.CompletedProcess:
        """Run terraform apply with generated variables.
        
        Args:
            terraform_dir: Directory containing Terraform configuration
            auto_approve: Whether to auto-approve the apply
            
        Returns:
            CompletedProcess from terraform command
        """
        terraform_dir = Path(terraform_dir)
        if not terraform_dir.exists():
            raise ValueError(f"Terraform directory not found: {terraform_dir}")
        
        # Generate tfvars file
        tfvars_path = terraform_dir / "dativo.auto.tfvars"
        self.generate_terraform_tfvars(str(tfvars_path))
        
        # Run terraform init
        self.logger.info("Running terraform init...")
        subprocess.run(
            ["terraform", "init"],
            cwd=terraform_dir,
            check=True
        )
        
        # Set workspace if configured
        if self.context.terraform_workspace:
            self.logger.info(f"Selecting Terraform workspace: {self.context.terraform_workspace}")
            subprocess.run(
                ["terraform", "workspace", "select", "-or-create", self.context.terraform_workspace],
                cwd=terraform_dir,
                check=True
            )
        
        # Run terraform apply
        cmd = ["terraform", "apply"]
        if auto_approve:
            cmd.append("-auto-approve")
        
        self.logger.info(f"Running terraform apply in {terraform_dir}...")
        result = subprocess.run(cmd, cwd=terraform_dir)
        
        if result.returncode == 0:
            self.logger.info("Terraform apply completed successfully")
        else:
            self.logger.error(f"Terraform apply failed with code {result.returncode}")
        
        return result
