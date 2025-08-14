# PolicySimplify AI — One-Pager

**Problem**  
Council teams wade through long policies to figure out “what do we actually need to do” and “by when”.

**Solution**  
Upload a policy PDF → get a plain-English summary, an actionable checklist (Owner + Due), a risk label, and a one-click Audit Pack (PDF).

**How it works**  
- PDF → text extract → vector index (FAISS/NumPy)  
- LLM turns text into Summary, Checklist, Risk (no training on your data)  
- Stored locally in SQLite with 14-day retention (configurable)

**Benefits**  
- Hours to minutes: instant obligations  
- Risk triage: High/Med/Low at a glance  
- Evidence ready: Audit Pack PDF

**Pilot scope**  
- 10 policies, 3 users, 6–8 weeks  
- Optional on-prem Docker (outbound HTTPS to OpenAI only)

**Pricing**  
- Pilot: AU$10k fixed  
- Annual: AU$48k (council-wide)

**Contact**  
hello@yourdomain.com
