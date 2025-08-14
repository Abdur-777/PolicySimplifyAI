# Security & Privacy Q&A
Data flow: PDF upload → text extract/OCR → embeddings+prompts to OpenAI/Azure over HTTPS → outputs saved in local SQLite. No training on your data.

Retention: default 14 days (configurable), purge job on startup.  
Access: passcode gate (pilot); production via reverse-proxy Basic Auth or SSO/SAML.  
Residency: app runs where deployed (Docker/VM); only outbound HTTPS to provider.  
Backups: optional nightly SQLite copy.  
Logging: event log (upload/url/example/qa/email/admin); no sensitive contents.  
Incidents: notify within 24h; RCA on request.
