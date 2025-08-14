# Security & Privacy Q&A (Pilot)

**Data flow**  
PDF is uploaded → text extracted → embeddings + prompts sent to OpenAI for processing → outputs stored in local SQLite. No data used to train models.

**Data retention**  
Default 14 days (configurable via `RETENTION_DAYS`). Daily purge on startup.

**Access**  
Passcode gate (`APP_PASSCODE`) for pilot. Production options: reverse-proxy Basic Auth or SSO/SAML.

**Data residency**  
App + SQLite run where you deploy (Render/Docker/on-prem). OpenAI processing over HTTPS.

**Backups**  
Pilot default: no backups. Option to nightly copy SQLite.

**Vulnerability & updates**  
Pinned dependencies; monthly base image refresh; CVE patching as required.

**Logging**  
Action log (upload/url/example/qa/email/admin). No sensitive payloads in logs.

**Incident response**  
Email notification within 24h; root cause report on request.