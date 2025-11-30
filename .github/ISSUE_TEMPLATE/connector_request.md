---
name: Connector Request
about: Request support for a new data source or target
title: '[CONNECTOR] '
labels: connector, enhancement
assignees: ''
---

## Connector Type

- [ ] Source (data extraction)
- [ ] Target (data writing)
- [ ] Both (bidirectional)

## Connector Information

**Name:** [e.g., Salesforce, Snowflake, BigQuery]

**Type:** [e.g., SaaS API, Database, File storage]

**Official Documentation:** [Link to API/SDK docs]

**Authentication Method:** [e.g., API key, OAuth 2.0, username/password, service account]

## Use Case

**Why do you need this connector?**

Describe your specific use case and what data you need to sync.

**What objects/tables would you need to access?**

- Object 1: [e.g., customers]
- Object 2: [e.g., orders]
- Object 3: [e.g., products]

**Required sync mode:**
- [ ] Full refresh
- [ ] Incremental (append)
- [ ] Incremental (upsert/merge)
- [ ] Real-time (streaming)

## Technical Details

**API/SDK Information:**

- API version: [e.g., v2.0]
- Rate limits: [e.g., 100 requests/minute]
- Pagination: [e.g., cursor-based, offset-based]
- Python library available: [e.g., `pip install salesforce-sdk`]

**Data Format:**

- Response format: [e.g., JSON, CSV, Parquet]
- Typical record size: [e.g., 1KB, 100KB]
- Expected volume: [e.g., 10K records/day, 1M records/month]

**Incremental Sync Support:**

- [ ] API supports filtering by timestamp (e.g., `updated_at > '2025-11-30'`)
- [ ] API supports cursor-based pagination
- [ ] Other incremental mechanism: _______

## Authentication & Configuration

**What credentials are needed?**

```yaml
# Example connector configuration
type: salesforce
credentials:
  # What fields would be needed?
  api_key: "${SALESFORCE_API_KEY}"
  # ...
connection:
  # What connection parameters?
  instance_url: "https://mycompany.salesforce.com"
  # ...
```

## Schema Example

**Provide an example record from this source:**

```json
{
  "id": "12345",
  "name": "John Doe",
  "email": "john@example.com",
  "created_at": "2025-11-30T10:00:00Z",
  "updated_at": "2025-11-30T12:00:00Z"
}
```

## Existing Implementations

**Do other tools support this connector?**

- [ ] Airbyte: [link to connector]
- [ ] Fivetran: [link to docs]
- [ ] Singer taps: [link to tap]
- [ ] Other: _______

**Are there open-source implementations we can reference?**
- Link 1: _______
- Link 2: _______

## Priority & Impact

**Priority for your use case:**
- [ ] Low - Nice to have
- [ ] Medium - Would improve workflow
- [ ] High - Important for our data pipeline
- [ ] Critical - Blocking our project

**Number of users who would benefit:**
- [ ] Just me
- [ ] My team (< 10 people)
- [ ] My organization (< 100 people)
- [ ] Likely many users in the community

## Contribution

**Are you willing to help implement this connector?**

- [ ] Yes, I can submit a PR with the connector implementation
- [ ] Yes, I can provide testing credentials for a sandbox/dev environment
- [ ] Yes, I can help test and provide feedback
- [ ] No, but I can provide detailed specifications
- [ ] No, but I'm happy to answer questions

**Can you provide test credentials?**
- [ ] Yes, I can provide a sandbox/test account
- [ ] Yes, but only for private testing
- [ ] No, only production credentials available
- [ ] The service offers free/trial accounts

## Additional Context

- Links to similar requests or discussions
- Specific features or quirks of this connector
- Known challenges or limitations
- Suggested implementation approach

---

**Checklist before submitting:**
- [ ] I've searched existing issues and connector requests
- [ ] I've provided links to API documentation
- [ ] I've described the use case and data schema
- [ ] I've indicated my willingness to contribute or test
