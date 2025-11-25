"""AWS infrastructure integration with comprehensive tag propagation."""

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import CloudInfrastructureManager, InfrastructureContext

logger = logging.getLogger(__name__)


class AWSInfrastructureManager(CloudInfrastructureManager):
    """AWS-specific infrastructure manager with tag propagation."""

    def __init__(self, job_config, asset, logger=None):
        """Initialize AWS infrastructure manager.
        
        Args:
            job_config: Job configuration
            asset: Asset definition
            logger: Optional logger instance
        """
        super().__init__(job_config, asset, logger)
        
        # Initialize AWS clients if boto3 is available
        self.boto3_available = False
        self.emr_client = None
        self.ec2_client = None
        self.s3_client = None
        self.tagging_client = None
        
        try:
            import boto3
            self.boto3_available = True
            
            # Initialize clients with region
            region = os.getenv("AWS_REGION", "us-east-1")
            self.emr_client = boto3.client("emr", region_name=region)
            self.ec2_client = boto3.client("ec2", region_name=region)
            self.s3_client = boto3.client("s3", region_name=region)
            self.tagging_client = boto3.client("resourcegroupstaggingapi", region_name=region)
            
            self.logger.info(f"AWS clients initialized for region: {region}")
        except ImportError:
            self.logger.warning("boto3 not available - AWS API operations will be skipped")
    
    def validate_infrastructure(self) -> bool:
        """Validate AWS infrastructure configuration and connectivity.
        
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
            valid_aws_platforms = ["emr", "ecs", "fargate", "ec2"]
            if platform not in valid_aws_platforms:
                self.logger.warning(
                    f"Platform '{platform}' may not be AWS-specific. Valid AWS platforms: {valid_aws_platforms}"
                )
        
        # Validate EMR cluster if specified
        if infra.runtime and infra.runtime.compute and infra.runtime.compute.cluster_id:
            cluster_id = os.path.expandvars(infra.runtime.compute.cluster_id)
            if self.boto3_available and self.emr_client:
                try:
                    response = self.emr_client.describe_cluster(ClusterId=cluster_id)
                    state = response["Cluster"]["Status"]["State"]
                    self.logger.info(f"EMR cluster {cluster_id} state: {state}")
                    
                    if state not in ["RUNNING", "WAITING"]:
                        errors.append(f"EMR cluster {cluster_id} is not in RUNNING/WAITING state: {state}")
                except Exception as e:
                    errors.append(f"Failed to validate EMR cluster {cluster_id}: {e}")
            else:
                self.logger.info(f"Skipping EMR cluster validation for {cluster_id} (boto3 not available)")
        
        # Validate VPC and networking
        if infra.runtime and infra.runtime.network:
            network = infra.runtime.network
            if network.vpc_id and self.boto3_available and self.ec2_client:
                try:
                    vpc_id = os.path.expandvars(network.vpc_id)
                    response = self.ec2_client.describe_vpcs(VpcIds=[vpc_id])
                    self.logger.info(f"VPC {vpc_id} validated successfully")
                except Exception as e:
                    errors.append(f"Failed to validate VPC {network.vpc_id}: {e}")
        
        # Validate S3 bucket if specified
        if infra.runtime and infra.runtime.storage and infra.runtime.storage.bucket:
            bucket = os.path.expandvars(infra.runtime.storage.bucket)
            if self.boto3_available and self.s3_client:
                try:
                    self.s3_client.head_bucket(Bucket=bucket)
                    self.logger.info(f"S3 bucket {bucket} validated successfully")
                except Exception as e:
                    errors.append(f"Failed to validate S3 bucket {bucket}: {e}")
        
        if errors:
            raise ValueError(f"AWS infrastructure validation failed: {'; '.join(errors)}")
        
        return True
    
    def apply_tags_to_resources(self, resource_ids: List[str]) -> Dict[str, bool]:
        """Apply tags to AWS resources.
        
        Args:
            resource_ids: List of AWS resource ARNs to tag
            
        Returns:
            Dictionary mapping resource ARNs to success status
        """
        if not self.boto3_available or not self.tagging_client:
            self.logger.warning("boto3 not available - skipping tag application")
            return {rid: False for rid in resource_ids}
        
        # Convert tags to AWS format
        aws_tags = [{"Key": k, "Value": v} for k, v in self.context.tags.items()]
        
        results = {}
        for resource_arn in resource_ids:
            try:
                self.tagging_client.tag_resources(
                    ResourceARNList=[resource_arn],
                    Tags={k: v for k, v in self.context.tags.items()}
                )
                results[resource_arn] = True
                self.logger.info(f"Applied {len(aws_tags)} tags to resource {resource_arn}")
            except Exception as e:
                self.logger.error(f"Failed to tag resource {resource_arn}: {e}")
                results[resource_arn] = False
        
        return results
    
    def apply_tags_to_emr_cluster(self, cluster_id: str) -> bool:
        """Apply tags to EMR cluster.
        
        Args:
            cluster_id: EMR cluster ID
            
        Returns:
            True if successful
        """
        if not self.boto3_available or not self.emr_client:
            self.logger.warning("boto3 not available - skipping EMR cluster tagging")
            return False
        
        try:
            cluster_id = os.path.expandvars(cluster_id)
            
            # Get cluster ARN
            response = self.emr_client.describe_cluster(ClusterId=cluster_id)
            cluster_arn = response["Cluster"]["ClusterArn"]
            
            # Apply tags
            aws_tags = [{"Key": k, "Value": v} for k, v in self.context.tags.items()]
            self.emr_client.add_tags(
                ResourceId=cluster_id,
                Tags=aws_tags
            )
            
            self.logger.info(f"Applied {len(aws_tags)} tags to EMR cluster {cluster_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to tag EMR cluster {cluster_id}: {e}")
            return False
    
    def apply_tags_to_s3_bucket(self, bucket_name: str) -> bool:
        """Apply tags to S3 bucket.
        
        Args:
            bucket_name: S3 bucket name
            
        Returns:
            True if successful
        """
        if not self.boto3_available or not self.s3_client:
            self.logger.warning("boto3 not available - skipping S3 bucket tagging")
            return False
        
        try:
            bucket_name = os.path.expandvars(bucket_name)
            
            # Convert tags to S3 format
            tag_set = [{"Key": k, "Value": v} for k, v in self.context.tags.items()]
            
            self.s3_client.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={"TagSet": tag_set}
            )
            
            self.logger.info(f"Applied {len(tag_set)} tags to S3 bucket {bucket_name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to tag S3 bucket {bucket_name}: {e}")
            return False
    
    def apply_all_infrastructure_tags(self) -> Dict[str, bool]:
        """Apply tags to all infrastructure resources defined in configuration.
        
        Returns:
            Dictionary mapping resource types to success status
        """
        results = {}
        
        infra = self.job_config.infrastructure
        if not infra or not infra.runtime:
            self.logger.info("No infrastructure runtime configuration - skipping tagging")
            return results
        
        # Tag EMR cluster if specified
        if infra.runtime.compute and infra.runtime.compute.cluster_id:
            cluster_id = infra.runtime.compute.cluster_id
            results["emr_cluster"] = self.apply_tags_to_emr_cluster(cluster_id)
        
        # Tag S3 bucket if specified
        if infra.runtime.storage and infra.runtime.storage.bucket:
            bucket = infra.runtime.storage.bucket
            results["s3_bucket"] = self.apply_tags_to_s3_bucket(bucket)
        
        # Tag EC2 instances in security groups
        if infra.runtime.network and infra.runtime.network.security_group_ids:
            # This would tag all instances in the security groups
            # Implementation depends on specific requirements
            pass
        
        return results
    
    def get_terraform_variables(self) -> Dict[str, Any]:
        """Get Terraform variables for AWS infrastructure.
        
        Returns:
            Dictionary of Terraform variables
        """
        variables = {
            "tenant_id": self.context.tenant_id,
            "environment": self.context.environment,
            "aws_region": os.getenv("AWS_REGION", "us-east-1"),
        }
        
        # Add all tags as variables
        variables["tags"] = self.context.tags
        variables["classification_tags"] = self.context.classification_tags
        variables["finops_tags"] = self.context.finops_tags
        
        # Add runtime configuration
        infra = self.job_config.infrastructure
        if infra:
            if infra.runtime:
                if infra.runtime.compute:
                    variables["instance_type"] = infra.runtime.compute.instance_type
                    variables["instance_count"] = infra.runtime.compute.instance_count
                    if infra.runtime.compute.auto_scaling:
                        variables["enable_autoscaling"] = infra.runtime.compute.auto_scaling.enabled
                        variables["min_instances"] = infra.runtime.compute.auto_scaling.min_instances
                        variables["max_instances"] = infra.runtime.compute.auto_scaling.max_instances
                
                if infra.runtime.storage:
                    variables["s3_bucket"] = infra.runtime.storage.bucket
                
                if infra.runtime.network:
                    variables["vpc_id"] = infra.runtime.network.vpc_id
                    variables["subnet_ids"] = infra.runtime.network.subnet_ids
                    variables["security_group_ids"] = infra.runtime.network.security_group_ids
                
                if infra.runtime.service_account:
                    variables["iam_role_arn"] = infra.runtime.service_account
            
            # Add user-provided variables (these override defaults)
            if infra.metadata and infra.metadata.variables:
                variables.update(infra.metadata.variables)
        
        return variables
    
    def export_terraform_outputs(self, output_path: str) -> None:
        """Export Terraform outputs for AWS infrastructure.
        
        Args:
            output_path: Path to write Terraform outputs
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        outputs = {
            "infrastructure_context": {
                "tenant_id": self.context.tenant_id,
                "environment": self.context.environment,
                "provider": "aws",
                "platform": self.context.platform,
                "cluster_id": self.context.cluster_id
            },
            "tags": self.context.tags,
            "classification_tags": self.context.classification_tags,
            "finops_tags": self.context.finops_tags,
            "terraform_variables": self.get_terraform_variables()
        }
        
        with open(output_path, "w") as f:
            json.dump(outputs, f, indent=2)
        
        self.logger.info(f"Exported Terraform outputs to {output_path}")
    
    def generate_terraform_tfvars(self, output_path: str) -> None:
        """Generate Terraform tfvars file for AWS infrastructure.
        
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
