# Security Policy

## Supported Versions

We actively support the following versions with security updates:

| Version | Supported          | Security Updates |
| ------- | ------------------ | ---------------- |
| 0.3.x   | :white_check_mark: | ✅ Yes           |
| 0.2.x   | :white_check_mark: | ✅ Yes           |
| 0.1.x   | :x:                | ❌ No            |
| < 0.1   | :x:                | ❌ No            |

**Note**: Only the latest two minor versions receive security updates. We strongly recommend upgrading to the latest version.

## Reporting a Vulnerability

**We take security vulnerabilities seriously.** If you discover a security issue, please report it privately to help us protect Dativo users.

### ⚠️ Important: Do NOT Report Security Issues Publicly

**Please do NOT report security vulnerabilities through:**
- Public GitHub issues
- Public discussions or forums
- Social media
- Any other public channels

### How to Report

Please report security vulnerabilities via one of the following **private** methods:

1. **GitHub Security Advisory** (Preferred): 
   - Use GitHub's [private vulnerability reporting](https://github.com/dativo-io/dativo-ingest/security/advisories/new) feature
   - This is the fastest and most secure method
   - GitHub will create a private advisory that only you and the maintainers can see
   - You can also navigate to: Repository → Security → Advisories → Report a vulnerability

2. **Email**: 
   - Send details to **security@dativo.io**
   - Include "[SECURITY]" in the subject line for faster processing
   - For encrypted communication, you may request our PGP key by email

3. **Encrypted Form** (if available):
   - Use our encrypted reporting form at: https://dativo.io/security (if available)

### What to Include

When reporting a vulnerability, please include:

- **Type of issue** (e.g., buffer overflow, SQL injection, cross-site scripting, authentication bypass, etc.)
- **Component affected** (e.g., CLI, orchestrator, plugin sandbox, secret manager, etc.)
- **Full paths of source file(s)** related to the vulnerability
- **Location of the affected code** (tag/branch/commit or direct URL)
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible, but not required)
- **Impact assessment** (what data or functionality could be compromised)
- **Suggested fix** (if you have one)

### Response Timeline

We commit to the following response times:

- **Initial Acknowledgment**: Within **48 hours** of receiving your report
- **Status Update**: Within **7 days** with an assessment of the issue
- **Resolution**: Depends on severity and complexity:
  - **Critical**: Patch released within 7-14 days
  - **High**: Patch released within 30 days
  - **Medium/Low**: Included in next scheduled release

### Disclosure Policy

- We will coordinate disclosure with you **after** the issue is resolved and patches are available
- We will credit you for the discovery in our security acknowledgments (unless you prefer to remain anonymous)
- We will **not** disclose your identity without your explicit permission
- We follow [Coordinated Vulnerability Disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure) practices

### Versioning Policy

Security updates are released as **patch versions** (e.g., 0.3.1 → 0.3.2) to maintain backward compatibility:

- **Security patches** are backported to all supported versions (see [Supported Versions](#supported-versions))
- **Critical vulnerabilities** may trigger immediate patch releases
- All security fixes are documented in the [CHANGELOG.md](CHANGELOG.md) with a security tag

## Secret Handling and Redaction

### Secret Storage

Job configurations support multiple secret management approaches:

- **Environment Variables**: Reference via `${VAR_NAME}` syntax in YAML configs
- **Secret Files**: Store in `/secrets/{tenant_id}/` directory (`.env` or `.json` format)
- **Secret Managers**: Use pluggable backends (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager)

**Never hardcode secrets** in YAML configuration files. Always use environment variables or secret files.

**Example:**
```yaml
# Job config (safe - uses environment variable)
target:
  connection:
    s3:
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
```

### Log Redaction

Dativo-Ingest includes built-in secret redaction to prevent credentials from appearing in logs.

**Enable in job configuration:**
```yaml
logging:
  redaction: true  # Redacts passwords, API keys, tokens, etc.
```

The redaction system automatically detects and redacts:
- Passwords, API keys, tokens, secret keys
- Fields containing "credential", "secret", "key", "token", or "password"
- Long base64-like strings (20+ characters)

Redacted values appear as `[REDACTED]` in log output.

See [docs/LOG_REDACTION.md](docs/LOG_REDACTION.md) for complete redaction details.

## Self-Hosted Deployment Model

Dativo-Ingest is designed for **self-hosted deployments** where:

- **Data stays in customer infrastructure**: No data transits through third-party services
- **No hosted control planes**: Everything runs in your infrastructure, on your terms
- **Customer responsibility**: You manage deployment, security, and operations
- **Vendor lock-in free**: Critical for enterprises that cannot accept vendor lock-in

This model enables:
- Compliance with data residency requirements
- Enterprise security policies (air-gapped deployments)
- Full control over data pipelines
- No external service dependencies

**Deployment responsibility:**
- You provide and manage infrastructure (Docker, Kubernetes, etc.)
- You configure networking, firewalls, and access controls
- You manage secrets and credentials
- You monitor and maintain the deployment

See [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) for production security guidance.

### Security Best Practices

When using Dativo-Ingest in production:

1. **Use secret managers**: Never hardcode credentials; use Vault, AWS Secrets Manager, or GCP Secret Manager
2. **Enable log redaction**: Enable secret redaction in logging configuration (`logging.redaction: true`)
3. **Review plugin code**: Audit custom plugins before deploying to production
4. **Monitor logs**: Enable structured logging and monitor for suspicious activity
5. **Rotate credentials**: Regularly rotate API keys and database passwords
6. **Secure Dagster UI**: Deploy behind reverse proxy with authentication (see [Runner and Orchestration](docs/RUNNER_AND_ORCHESTRATION.md))

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

- **Secret Management**: Secrets are loaded via pluggable backends (Vault, AWS Secrets Manager, GCP Secret Manager, filesystem). Ensure your secret manager is properly configured.
- **Log Redaction**: The logging system includes automatic secret redaction. Enable via `logging.redaction: true` in job configs. See [docs/LOG_REDACTION.md](docs/LOG_REDACTION.md).
- **State Files**: State files (`/state/{tenant_id}/`) may contain sensitive metadata (incremental cursors). Ensure proper file permissions (`chmod 700`).
- **Dagster UI Security**: The Dagster web UI (port 3000) does not include built-in authentication. **For production deployments, you MUST secure the Dagster UI** by:
  - Deploying behind a reverse proxy (Nginx, Apache) with authentication (OAuth, SAML, LDAP, or basic auth)
  - Placing behind a VPN or private network
  - Enabling HTTPS/TLS encryption
  - Restricting access via firewall rules or network policies
  - See [docs/RUNNER_AND_ORCHESTRATION.md](docs/RUNNER_AND_ORCHESTRATION.md) for details

### Security Updates

**Versioning Policy**: Security updates are released as **patch versions** (e.g., 0.3.1 → 0.3.2) to maintain backward compatibility. Critical security fixes may be backported to previous minor versions.

**Staying Informed**:
- Subscribe to GitHub releases for automatic notifications
- Monitor the [CHANGELOG.md](CHANGELOG.md) for security-related updates (look for `[SECURITY]` tags)
- Enable GitHub Security Advisories notifications
- Update promptly when security patches are released

**Update Process**:
1. Security patches are tested and validated before release
2. Patches are released with detailed changelog entries
3. Critical vulnerabilities trigger immediate patch releases
4. All supported versions receive security updates simultaneously when possible

## Security Acknowledgments

We thank the following security researchers for responsibly disclosing vulnerabilities:

- (To be populated as vulnerabilities are reported)

---

**Last Updated**: 2025-01-XX
