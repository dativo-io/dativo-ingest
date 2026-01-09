# RBAC & Access Control

This document covers access control capabilities, limitations, and workarounds for Dativo Ingestion Platform.

## Current Limitations

**Dativo does not currently provide multi-user RBAC (Role-Based Access Control).** Each deployment is effectively **single-tenant in practice**, with access to jobs and configurations scoped by:

- **File System Structure**: Access control is managed through folder/branch structure in your repository
- **Git-Based Access**: Use Git repository permissions and branch protection rules to control who can modify job configs
- **Infrastructure-Level Controls**: Rely on your deployment infrastructure (Kubernetes RBAC, IAM policies, etc.) for access control

## Access Control Model

### Current Architecture

Dativo's current access control model is based on:

1. **Tenant Isolation**: Built-in tenant isolation for data, state, and secrets
2. **File System Structure**: Jobs organized by tenant (`jobs/{tenant_id}/`)
3. **Git Permissions**: Repository-level access control
4. **Infrastructure RBAC**: Kubernetes, IAM, or similar infrastructure-level controls

### What's Missing

- ❌ User authentication within Dativo
- ❌ Role-based permissions (viewer, operator, admin)
- ❌ Per-tenant user management
- ❌ API-level access controls
- ❌ UI-based access control (no UI exists)
- ❌ Fine-grained permissions (e.g., read-only access to specific jobs)

## Workarounds for Multi-User Scenarios

### 1. Git-Based Access Control

**Strategy**: Use Git repository permissions and branch protection rules.

**Implementation**:
- Organize jobs by team/tenant in separate directories
- Use branch protection rules to require PR reviews
- Grant repository access based on team/role
- Use Git hooks to enforce policies

**Example Structure**:
```
jobs/
  team_a/           # Team A's jobs
  team_b/           # Team B's jobs
  platform/         # Platform team's jobs
```

**Benefits**:
- Audit trail via Git history
- PR-based approvals
- Branch protection prevents direct pushes
- Integrates with existing Git workflows

**Limitations**:
- All-or-nothing access at repository level
- No runtime access control
- Requires Git repository access for all users

### 2. Separate Deployments Per Tenant/Team

**Strategy**: Deploy separate Dativo instances per tenant or team.

**Implementation**:
- Deploy isolated Dativo instances in separate Kubernetes namespaces
- Use separate Git repositories or branches per tenant
- Configure separate secret managers per tenant
- Use network policies to isolate instances

**Example**:
```yaml
# Kubernetes namespace per tenant
namespace: dativo-tenant-a
namespace: dativo-tenant-b
```

**Benefits**:
- Complete isolation between tenants
- Independent scaling and configuration
- No cross-tenant data leakage risk
- Infrastructure-level isolation

**Limitations**:
- Higher operational overhead
- Resource duplication
- More complex deployment management

### 3. Infrastructure-Level RBAC

**Strategy**: Use Kubernetes RBAC, IAM policies, or similar infrastructure controls.

**Implementation**:
- **Kubernetes**: Use RBAC to control access to Dativo pods/configs
- **AWS IAM**: Use IAM policies to control access to S3, secrets, etc.
- **CI/CD**: Use CI/CD pipeline permissions to control job deployment
- **API Gateway**: Deploy behind an API gateway with authentication

**Example Kubernetes RBAC**:
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: dativo-operator
rules:
- apiGroups: [""]
  resources: ["configmaps", "secrets"]
  verbs: ["get", "list"]
```

**Benefits**:
- Leverages existing infrastructure controls
- Familiar to operators
- Integrates with existing tooling

**Limitations**:
- Requires infrastructure expertise
- Not Dativo-native
- May not cover all access patterns

### 4. CI/CD Pipeline Controls

**Strategy**: Use CI/CD pipelines with branch protection and approval workflows.

**Implementation**:
- Require PR reviews before merging job configs
- Use branch protection rules
- Automate deployment through CI/CD pipelines
- Require approvals for production deployments

**Example Workflow**:
1. Developer creates job config in feature branch
2. PR requires review from data team
3. Automated tests run on PR
4. Merge requires approval
5. CI/CD pipeline deploys to staging
6. Manual approval required for production

**Benefits**:
- Built-in approval workflows
- Automated testing before deployment
- Clear audit trail
- Prevents direct production changes

**Limitations**:
- Requires CI/CD setup
- Doesn't control runtime access
- All-or-nothing deployment model

### 5. Separate Git Repositories

**Strategy**: Use separate Git repositories per tenant or team.

**Implementation**:
- Create separate repositories for each tenant/team
- Each repository contains only that tenant's jobs
- Use repository permissions to control access
- Deploy from tenant-specific repositories

**Example**:
```
dativo-ingest-tenant-a/  # Repository for tenant A
dativo-ingest-tenant-b/  # Repository for tenant B
dativo-ingest-platform/  # Repository for platform team
```

**Benefits**:
- Complete repository-level isolation
- Clear ownership boundaries
- Simple permission model
- Independent versioning

**Limitations**:
- Code duplication across repositories
- Harder to share common configs
- More repositories to manage

## Recommended Approach by Scenario

### Multi-Tenant SaaS Platform

**Recommended**: Separate deployments per tenant + infrastructure RBAC

- Deploy Dativo instances in separate Kubernetes namespaces per tenant
- Use Kubernetes RBAC for namespace access
- Use tenant-specific secret managers
- Complete isolation with clear boundaries

### Internal Data Platform

**Recommended**: Git-based access control + CI/CD pipelines

- Single repository with team-based directories
- Branch protection and PR reviews
- CI/CD pipelines with approval workflows
- Infrastructure RBAC for deployment access

### External Customers/Partners

**Recommended**: Separate deployments per customer

- Isolated Dativo instances per customer
- Customer-specific Git repositories or branches
- Network isolation via Kubernetes namespaces
- Customer-specific secret managers

## Security Best Practices

### 1. Secrets Management

- Use tenant-specific secret managers where possible
- Rotate secrets regularly
- Use least-privilege access for secret access
- Audit secret access

See [Secret Management](SECRET_MANAGEMENT.md) for details.

### 2. Network Isolation

- Use Kubernetes network policies to isolate tenants
- Deploy in separate VPCs or network segments
- Use private endpoints where possible
- Enable network encryption (TLS)

### 3. Audit Logging

- Enable Git audit logs for configuration changes
- Use infrastructure audit logs (Kubernetes, CloudTrail, etc.)
- Log all job executions
- Monitor for unauthorized access

### 4. Least Privilege

- Grant minimum required access at all layers
- Use read-only access where possible
- Separate development and production access
- Regular access reviews

## Roadmap: Future RBAC Features

Planned for a future release:

- 🔜 **User Authentication**: Built-in user authentication and management
- 🔜 **Role-Based Permissions**: Viewer, operator, admin roles
- 🔜 **Per-Tenant User Management**: Tenant-specific user management
- 🔜 **API-Level Access Controls**: Fine-grained API permissions
- 🔜 **Fine-Grained Permissions**: Per-job, per-connector permissions
- 🔜 **OAuth/SAML Integration**: Integration with identity providers

**Timeline**: TBD (not yet scheduled)

## Summary

**Current State**:
- ✅ Tenant isolation for data, state, and secrets
- ✅ Git-based configuration management
- ❌ No built-in user authentication
- ❌ No role-based permissions
- ❌ No API-level access controls

**Recommended Workarounds**:
- **Multi-tenant SaaS**: Separate deployments + infrastructure RBAC
- **Internal platform**: Git-based access + CI/CD pipelines
- **External customers**: Separate deployments per customer

**Security Best Practices**:
- Use tenant-specific secret managers
- Enable network isolation
- Implement audit logging
- Follow least-privilege principles

For more details, see:
- [Secret Management](SECRET_MANAGEMENT.md) - Secret management backends
- [SECURITY.md](../SECURITY.md) - Security guidelines
- [Security Audit](SECURITY_AUDIT.md) - Security audit details

