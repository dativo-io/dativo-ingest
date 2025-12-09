# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.3.x   | :white_check_mark: |
| 1.2.x   | :white_check_mark: |
| 1.1.x   | :x:                |
| 1.0.x   | :x:                |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it privately to help us protect Dativo users.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via one of the following methods:

1. **Email**: Send details to [security@dativo.io](mailto:security@dativo.io) (or maintainer email if different)
2. **GitHub Security Advisory**: Use GitHub's [private vulnerability reporting](https://github.com/YOUR_ORG/dativo-ingest/security/advisories/new) feature

### What to Include

When reporting a vulnerability, please include:

- **Type of issue** (e.g., buffer overflow, SQL injection, cross-site scripting, etc.)
- **Full paths of source file(s) related to the vulnerability**
- **Location of the affected code** (tag/branch/commit or direct URL)
- **Step-by-step instructions to reproduce the issue**
- **Proof-of-concept or exploit code** (if possible)
- **Impact of the issue** (what data or functionality could be compromised)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Resolution**: Depends on severity and complexity

### Disclosure Policy

- We will coordinate disclosure with you after the issue is resolved
- We will credit you for the discovery (unless you prefer to remain anonymous)
- We will not disclose your identity without your permission

### Security Best Practices

When using Dativo-Ingest in production:

1. **Keep dependencies updated**: Regularly update Python packages and Rust plugins
2. **Use secret managers**: Never hardcode credentials; use Vault, AWS Secrets Manager, or GCP Secret Manager
3. **Enable log redaction**: Enable secret redaction in logging configuration to prevent credentials from appearing in logs
4. **Enable sandboxing**: Use Docker-based sandboxing for Python plugins in cloud mode
5. **Review plugin code**: Audit custom plugins before deploying to production
6. **Monitor logs**: Enable structured logging and monitor for suspicious activity
7. **Limit network access**: Restrict plugin network access using seccomp profiles
8. **Rotate credentials**: Regularly rotate API keys and database passwords
9. **Use least privilege**: Grant plugins only the minimum permissions needed

### Vulnerability Scanning

**Automated Scanning**: Vulnerability scanning is integrated into our CI/CD pipeline:

- **Python Dependencies**: All Python dependencies are automatically scanned using `pip-audit` on every commit and pull request
- **Docker Images**: Plugin container images (e.g., Airbyte connectors) are scanned using Trivy for known vulnerabilities
- **Build Failures**: CI builds fail if critical or high-severity vulnerabilities are detected in dependencies
- **Dependabot**: GitHub Dependabot is active and automatically creates pull requests for dependency updates and security patches

**Manual Scanning**: You can also scan dependencies locally:

```bash
# Install pip-audit
pip install pip-audit

# Scan dependencies
pip-audit --desc

# Scan with JSON output
pip-audit --format json --output report.json
```

**Reporting Vulnerabilities**: If you discover a vulnerability in Dativo-Ingest or its dependencies, please report it following our [vulnerability reporting process](#reporting-a-vulnerability).

### Known Security Considerations

- **Python Plugin Sandboxing**: Python plugins run in Docker containers in cloud mode with resource limits and network isolation
- **Secret Management**: Secrets are loaded via pluggable backends; ensure your secret manager is properly configured
- **Log Redaction**: The logging system includes automatic secret redaction to prevent credentials from appearing in logs. Enable this feature via the `logging.redaction` configuration option in job configs or `--log-redaction` CLI flag.
- **State Files**: State files may contain sensitive metadata; ensure proper file permissions
- **Network Access**: Plugins may make external network calls; review plugin code and use network restrictions where possible
- **Dagster UI Security**: The Dagster web UI (port 3000) does not include built-in authentication. **For production deployments, you MUST secure the Dagster UI** by:
  - Deploying behind a reverse proxy (Nginx, Apache) with authentication (OAuth, SAML, LDAP, or basic auth)
  - Placing behind a VPN or private network
  - Enabling HTTPS/TLS encryption
  - Restricting access via firewall rules or network policies
  - See [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) for detailed guidance

### Encryption at Rest

**Current Status**: State files (`/state/`) and WAL (Write-Ahead Log) files (`/wal/`) are **not encrypted at rest by default**. These files may contain sensitive metadata such as:

- Incremental state cursors (e.g., `last_updated_at` timestamps)
- Checkpoint information (chunk numbers, offsets, record counts)
- Job run metadata and status information

**Production Recommendations**:

1. **Use Encrypted Volumes**: Store state and WAL directories on encrypted volumes/filesystems:
   - **AWS**: Use EBS volumes with encryption enabled or EFS with encryption at rest
   - **GCP**: Use Persistent Disks with customer-managed encryption keys (CMEK)
   - **Azure**: Use Azure Disk Encryption or Azure Files with encryption
   - **On-Premises**: Use LUKS, BitLocker, or filesystem-level encryption (e.g., ZFS encryption)

2. **File Permissions**: Ensure proper file permissions are set:
   ```bash
   chmod 700 /app/state /app/wal  # Restrict access to owner only
   ```

3. **Network Storage**: If using network storage (NFS, S3, etc.), ensure:
   - Network encryption (TLS/SSL) is enabled
   - Access controls are properly configured
   - Storage provider encryption is enabled

**Roadmap**: Native encryption support for state and WAL files is planned for a future release. This will include:
- Transparent encryption/decryption of state and WAL files
- Support for multiple encryption backends (AWS KMS, GCP KMS, HashiCorp Vault)
- Key rotation capabilities
- Performance-optimized encryption for high-throughput scenarios

Until native encryption is available, production deployments should rely on encrypted volumes/filesystems as described above.

### Security Updates

Security updates are released as patch versions (e.g., 1.3.1 → 1.3.2). We recommend:

- Subscribing to GitHub releases for notifications
- Monitoring the [CHANGELOG.md](CHANGELOG.md) for security-related updates
- Updating promptly when security patches are released

## Security Acknowledgments

We thank the following security researchers for responsibly disclosing vulnerabilities:

- (To be populated as vulnerabilities are reported)

---

**Last Updated**: 2025-01-XX
