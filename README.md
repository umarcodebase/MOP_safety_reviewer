# 🛡️ MOP Safety Reviewer

AI-assisted Method of Procedure (MOP) safety review for data center maintenance.

**Created by Umar Shahzad**

Upload a data center Method of Procedure (MOP) as a PDF and get, in seconds:

- **Readiness score** (0–100) and a Go / Go with fixes / No-go decision
- **Full-attention steps** — the switching, bypass, isolation and re-energising steps where an outage or injury can happen
- **Findings** — missing back-out plan, LOTO, zero-energy verification, PPE, redundancy loss (N+1 → N), notifications, approvals, ambiguous wording
- **Guided checklist** — steps unlock in order, hold points at high-risk steps, timestamps + initials
- **Branded PDF report** with checklist and sign-off block

## Why
Uptime Institute's 2026 outage analysis found that failure to follow established procedures remains the leading driver of human-error outages. MOP Safety Reviewer attacks both halves: weak procedures (review) and skipped steps (guided execution).

## How it works (agentic pipeline)
1. **Parser agent** — extracts text and numbered steps (pypdf)
2. **Rule agent** — deterministic safety checks → identical results for the same document
3. **Retriever** — run-time **FAISS** index over document chunks (TF-IDF vectors, no embedding API); fixed risk queries pull evidence per category
4. **Reviewer agent** — LLM (temperature 0, JSON mode) adds senior-engineer findings and "watch for" guidance
5. **Lead agent** — executive summary + pre-job briefing

Results are cached per document, so the same MOP always gives the same report. Without an API key the app runs in rules-only mode.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this folder to a public GitHub repo
2. share.streamlit.io → New app → pick the repo, main file `app.py`
3. App settings → Secrets: `GROQ_API_KEY = "gsk_..."` (free key: console.groq.com)

## Privacy & scope
- Use **synthetic or public** MOPs only. Never upload confidential employer documents.
- Uploaded files are processed in memory and not stored.
- Decision support only: a qualified engineer must approve every MOP.

---
© Umar Shahzad
