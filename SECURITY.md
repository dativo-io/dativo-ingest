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
3. **Enable sandboxing**: Use Docker-based sandboxing for Python plugins in cloud mode
4. **Review plugin code**: Audit custom plugins before deploying to production
5. **Monitor logs**: Enable structured logging and monitor for suspicious activity
6. **Limit network access**: Restrict plugin network access using seccomp profiles
7. **Rotate credentials**: Regularly rotate API keys and database passwords
8. **Use least privilege**: Grant plugins only the minimum permissions needed

### Known Security Considerations

- **Python Plugin Sandboxing**: Python plugins run in Docker containers in cloud mode with resource limits and network isolation
- **Secret Management**: Secrets are loaded via pluggable backends; ensure your secret manager is properly configured
- **State Files**: State files may contain sensitive metadata; ensure proper file permissions
- **Network Access**: Plugins may make external network calls; review plugin code and use network restrictions where possible

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
