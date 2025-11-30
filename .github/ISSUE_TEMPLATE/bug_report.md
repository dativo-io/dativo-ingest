---
name: Bug Report
about: Report a bug or unexpected behavior
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description

A clear and concise description of what the bug is.

## Steps to Reproduce

1. Run command: `dativo run --config ...`
2. With configuration: `...`
3. Expected outcome: `...`
4. Actual outcome: `...`

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened. Include error messages or unexpected output.

## Environment

**Dativo Version:**
```bash
dativo --version
```

**Environment:**
- OS: [e.g., Ubuntu 22.04, macOS 13.2]
- Python version: [e.g., 3.10.9]
- Docker version (if applicable): [e.g., 24.0.5]
- Deployment mode: [self_hosted / cloud]

**Connector/Plugin:**
- Connector type: [e.g., stripe, postgres, custom plugin]
- Target: [e.g., s3, iceberg]

## Configuration

**Job config:** (sanitize secrets!)
```yaml
# Paste your job.yaml here (remove sensitive values)
tenant_id: acme
source_connector: postgres
# ...
```

**Asset schema:** (if relevant)
```yaml
# Paste your asset definition
```

## Logs

**Relevant log output:**
```
[Paste relevant log lines here]
```

**Full logs:** (if available)
- Attach full log file or paste full output in a code block

## Additional Context

- Does this happen consistently or intermittently?
- Have you tried any workarounds?
- Is this a regression (worked in a previous version)?
- Any other relevant information

## Possible Solution

If you have ideas on what might be causing this or how to fix it, please share!

---

**Checklist before submitting:**
- [ ] I've searched existing issues and this is not a duplicate
- [ ] I've included all relevant environment information
- [ ] I've sanitized secrets from config files and logs
- [ ] I've provided steps to reproduce
