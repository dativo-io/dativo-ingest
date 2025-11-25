# Terraform module for Dativo ETL on GCP GKE
# Provisions GKE cluster with comprehensive label propagation

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "tenant_id" {
  description = "Tenant identifier from Dativo job configuration"
  type        = string
}

variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
}

variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "labels" {
  description = "Complete label set from Dativo (includes classification, FinOps, governance)"
  type        = map(string)
  default     = {}
}

variable "classification_labels" {
  description = "Data classification labels for compliance"
  type        = map(string)
  default     = {}
}

variable "finops_labels" {
  description = "FinOps labels for cost allocation"
  type        = map(string)
  default     = {}
}

variable "kubernetes_labels" {
  description = "Kubernetes-specific labels"
  type        = map(string)
  default     = {}
}

variable "kubernetes_annotations" {
  description = "Kubernetes annotations"
  type        = map(string)
  default     = {}
}

variable "machine_type" {
  description = "GKE node machine type"
  type        = string
  default     = "n2-standard-4"
}

variable "node_count" {
  description = "Number of GKE nodes"
  type        = number
  default     = 3
}

variable "enable_autoscaling" {
  description = "Enable GKE cluster autoscaling"
  type        = bool
  default     = false
}

variable "min_nodes" {
  description = "Minimum number of nodes for autoscaling"
  type        = number
  default     = 2
}

variable "max_nodes" {
  description = "Maximum number of nodes for autoscaling"
  type        = number
  default     = 10
}

variable "network" {
  description = "VPC network name"
  type        = string
}

variable "subnetwork_ids" {
  description = "Subnetwork IDs"
  type        = list(string)
  default     = []
}

variable "gcs_bucket" {
  description = "GCS bucket for data storage"
  type        = string
}

variable "kubernetes_namespace" {
  description = "Kubernetes namespace for Dativo workloads"
  type        = string
  default     = "dativo"
}

variable "enable_workload_identity" {
  description = "Enable GKE Workload Identity"
  type        = bool
  default     = true
}

variable "enable_private_nodes" {
  description = "Enable private GKE nodes"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable encryption for GCS and GKE"
  type        = bool
  default     = true
}

# Data sources
data "google_client_config" "current" {}

# Merge all labels
locals {
  common_labels = merge(
    var.labels,
    var.classification_labels,
    var.finops_labels,
    {
      "managed_by"         = "terraform"
      "terraform_module"   = "dativo-gke"
      "dativo_tenant"      = var.tenant_id
      "dativo_environment" = var.environment
    }
  )
  
  cluster_name = "dativo-${var.tenant_id}-${var.environment}"
}

# GCS bucket for data
resource "google_storage_bucket" "dativo_data" {
  name          = var.gcs_bucket
  location      = var.gcp_region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
  
  dynamic "encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.dativo[0].id
    }
  }
  
  labels = local.common_labels
}

# KMS keyring for encryption
resource "google_kms_key_ring" "dativo" {
  count    = var.enable_encryption ? 1 : 0
  name     = "dativo-${var.tenant_id}-${var.environment}"
  location = var.gcp_region
}

resource "google_kms_crypto_key" "dativo" {
  count           = var.enable_encryption ? 1 : 0
  name            = "dativo-encryption-key"
  key_ring        = google_kms_key_ring.dativo[0].id
  rotation_period = "7776000s"  # 90 days
  
  labels = local.common_labels
}

# Service account for GKE nodes
resource "google_service_account" "gke_nodes" {
  account_id   = "${local.cluster_name}-nodes"
  display_name = "Service account for ${local.cluster_name} GKE nodes"
  project      = var.gcp_project_id
}

# IAM bindings for service account
resource "google_project_iam_member" "gke_nodes_storage" {
  project = var.gcp_project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_logging" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring" {
  project = var.gcp_project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# GKE Cluster
resource "google_container_cluster" "dativo" {
  name     = local.cluster_name
  location = var.gcp_region
  project  = var.gcp_project_id
  
  # We can't create a cluster with no node pool, so we create the smallest possible default
  # node pool and immediately delete it.
  remove_default_node_pool = true
  initial_node_count       = 1
  
  network    = var.network
  subnetwork = length(var.subnetwork_ids) > 0 ? var.subnetwork_ids[0] : null
  
  # Enable Workload Identity
  dynamic "workload_identity_config" {
    for_each = var.enable_workload_identity ? [1] : []
    content {
      workload_pool = "${var.gcp_project_id}.svc.id.goog"
    }
  }
  
  # Private cluster configuration
  dynamic "private_cluster_config" {
    for_each = var.enable_private_nodes ? [1] : []
    content {
      enable_private_nodes    = true
      enable_private_endpoint = false
      master_ipv4_cidr_block  = "172.16.0.0/28"
    }
  }
  
  # Enable encryption
  dynamic "database_encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      state    = "ENCRYPTED"
      key_name = google_kms_crypto_key.dativo[0].id
    }
  }
  
  # Addons
  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
  }
  
  # Logging and monitoring
  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"
  
  resource_labels = local.common_labels
}

# GKE Node Pool
resource "google_container_node_pool" "dativo_nodes" {
  name       = "${local.cluster_name}-node-pool"
  location   = var.gcp_region
  cluster    = google_container_cluster.dativo.name
  project    = var.gcp_project_id
  
  initial_node_count = var.node_count
  
  dynamic "autoscaling" {
    for_each = var.enable_autoscaling ? [1] : []
    content {
      min_node_count = var.min_nodes
      max_node_count = var.max_nodes
    }
  }
  
  node_config {
    machine_type = var.machine_type
    
    service_account = google_service_account.gke_nodes.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    
    labels = merge(
      local.common_labels,
      var.kubernetes_labels
    )
    
    metadata = {
      disable-legacy-endpoints = "true"
    }
    
    # Enable Workload Identity
    dynamic "workload_metadata_config" {
      for_each = var.enable_workload_identity ? [1] : []
      content {
        mode = "GKE_METADATA"
      }
    }
    
    # Enable encryption
    disk_encryption_key {
      kms_key_self_link = var.enable_encryption ? google_kms_crypto_key.dativo[0].id : null
    }
  }
}

# Kubernetes namespace
resource "kubernetes_namespace" "dativo" {
  metadata {
    name = var.kubernetes_namespace
    
    labels = merge(
      var.kubernetes_labels,
      {
        "app"                    = "dativo"
        "tenant"                 = var.tenant_id
        "environment"            = var.environment
        "managed_by"             = "terraform"
      }
    )
    
    annotations = var.kubernetes_annotations
  }
  
  depends_on = [google_container_node_pool.dativo_nodes]
}

# Service account for Dativo workloads
resource "kubernetes_service_account" "dativo_runner" {
  metadata {
    name      = "dativo-runner"
    namespace = kubernetes_namespace.dativo.metadata[0].name
    
    labels = merge(
      var.kubernetes_labels,
      {
        "app" = "dativo"
      }
    )
    
    annotations = merge(
      var.kubernetes_annotations,
      var.enable_workload_identity ? {
        "iam.gke.io/gcp-service-account" = google_service_account.gke_nodes.email
      } : {}
    )
  }
}

# Role for Dativo workloads
resource "kubernetes_role" "dativo_runner" {
  metadata {
    name      = "dativo-runner"
    namespace = kubernetes_namespace.dativo.metadata[0].name
  }
  
  rule {
    api_groups = [""]
    resources  = ["pods", "pods/log"]
    verbs      = ["get", "list", "watch"]
  }
  
  rule {
    api_groups = ["batch"]
    resources  = ["jobs"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }
}

resource "kubernetes_role_binding" "dativo_runner" {
  metadata {
    name      = "dativo-runner"
    namespace = kubernetes_namespace.dativo.metadata[0].name
  }
  
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role.dativo_runner.metadata[0].name
  }
  
  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.dativo_runner.metadata[0].name
    namespace = kubernetes_namespace.dativo.metadata[0].name
  }
}

# Outputs
output "gke_cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.dativo.name
}

output "gke_cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.dativo.endpoint
  sensitive   = true
}

output "gke_cluster_ca_certificate" {
  description = "GKE cluster CA certificate"
  value       = google_container_cluster.dativo.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "gcs_bucket" {
  description = "GCS bucket for data storage"
  value       = google_storage_bucket.dativo_data.name
}

output "kubernetes_namespace" {
  description = "Kubernetes namespace for Dativo workloads"
  value       = kubernetes_namespace.dativo.metadata[0].name
}

output "service_account_email" {
  description = "GCP service account email"
  value       = google_service_account.gke_nodes.email
}

output "applied_labels" {
  description = "All labels applied to resources"
  value       = local.common_labels
}

output "classification_labels" {
  description = "Classification labels for compliance"
  value       = var.classification_labels
}

output "finops_labels" {
  description = "FinOps labels for cost allocation"
  value       = var.finops_labels
}
