"""
MOP Safety Reviewer - AI Procedure Risk Reviewer for data center maintenance.
Created by Umar Shahzad.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import streamlit as st
from openai import OpenAI

from mop_engine import PROVIDERS, analyze
from report import APP_NAME, CREATOR, build_pdf

MAX_MB, MAX_PAGES = 10, 40
SAMPLE = Path(__file__).parent / "samples" / "sample_mop_ups_bypass.pdf"
SEV_ICON = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}

st.set_page_config(page_title=f"{APP_NAME} | by {CREATOR}", page_icon="🛡️", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.6rem;max-width:1200px}
.hero{background:linear-gradient(120deg,#0f2038 0%,#123c5a 60%,#009688 100%);color:#fff;
      padding:26px 30px;border-radius:16px;margin-bottom:18px}
.hero h1{margin:0;font-size:2.1rem;color:#fff}
.hero p{margin:.35rem 0 0;opacity:.88}
.badge{display:inline-block;background:rgba(255,255,255,.16);padding:3px 10px;border-radius:99px;
       font-size:.78rem;margin-top:10px}
.card{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:14px 16px;margin-bottom:10px}
.sev{font-weight:700;font-size:.75rem;padding:2px 8px;border-radius:99px;color:#fff}
.Critical{background:#c01c28}.High{background:#e65100}.Medium{background:#c79100}.Low{background:#2e7d32}
.hot{border-left:5px solid #c01c28}
.foot{text-align:center;opacity:.6;font-size:.8rem;margin-top:30px}
</style>""", unsafe_allow_html=True)

st.markdown(f"""<div class="hero"><h1>🛡️ {APP_NAME}</h1>
<p>AI procedure risk reviewer for data center maintenance. Catch the mistake on paper,
before it happens on the floor.</p>
<span class="badge">Created by {CREATOR}</span> <span class="badge">RAG · FAISS · Agentic review</span>
<span class="badge">Advisory only: humans decide</span></div>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("👤 Personalise")
    name = st.text_input("Your name", placeholder="e.g. Alex Rossi")
    role = st.selectbox("Your role", ["Critical facilities engineer", "Data center technician",
                                      "Shift lead / supervisor", "Student / learner", "Contractor"])
    site = st.text_input("Site / facility (optional)", placeholder="e.g. MXP-1, Hall B")
    context = st.text_area("Equipment & redundancy context (optional)", height=110,
                           placeholder="e.g. UPS-A and UPS-B in 2N, each feeding PDU-A1/B1. Generator GEN-1 is N+1.")
    st.divider()
    st.header("🤖 AI engine")
    provider = st.selectbox("Provider", list(PROVIDERS))
    base_url, default_model = PROVIDERS[provider]
    try:
        secret_key = st.secrets.get("GROQ_API_KEY" if provider.startswith("Groq") else "XAI_API_KEY", "")
    except Exception:
        secret_key = ""
    api_key = secret_key or st.text_input("API key", type="password",
                                          help="Free key at console.groq.com. Not stored.")
    model = st.text_input("Model", default_model)
    st.caption("✅ Key loaded from app secrets" if secret_key else
               "No key? The app still runs in rules-only mode.")
    st.divider()
    st.caption(f"Built by **{CREATOR}** · Energy engineering, data center operations")

profile = {"name": name.strip(), "role": role, "site": site.strip(), "context": context.strip()}


@st.cache_data(show_spinner=False, max_entries=32)
def run_analysis(pdf_bytes: bytes, profile_items: tuple, key_hash: str, base_url: str, model: str, _key: str):
    """Cached: same document + same context -> identical result (consistency)."""
    client = OpenAI(api_key=_key, base_url=base_url, timeout=60) if _key else None
    return analyze(pdf_bytes, dict(profile_items), client, model, MAX_PAGES)


# ------------------------------------------------------------------ input
c1, c2 = st.columns([3, 1])
with c1:
    up = st.file_uploader(f"Upload a MOP (PDF, text-based, max {MAX_MB} MB / {MAX_PAGES} pages)", type=["pdf"])
with c2:
    st.write("")
    st.write("")
    use_sample = st.button("Try sample MOP", use_container_width=True, disabled=not SAMPLE.exists())

if use_sample:
    st.session_state["pdf"] = ("sample_mop_ups_bypass.pdf", SAMPLE.read_bytes())
if up is not None:
    if up.size > MAX_MB * 1024 * 1024:
        st.error(f"File is {up.size / 1e6:.1f} MB; the limit is {MAX_MB} MB.")
        st.stop()
    st.session_state["pdf"] = (up.name, up.getvalue())

if "pdf" not in st.session_state:
    a, b, c = st.columns(3)
    a.markdown("<div class='card'><b>1 · Upload</b><br>Any MOP / SOP / EOP as a PDF.</div>", unsafe_allow_html=True)
    b.markdown("<div class='card'><b>2 · Review</b><br>Rules + FAISS retrieval + AI reviewer flag gaps and high-risk steps.</div>", unsafe_allow_html=True)
    c.markdown("<div class='card'><b>3 · Execute & export</b><br>Guided checklist with timestamps, and a branded PDF report.</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='foot'>{APP_NAME} · created by {CREATOR}</div>", unsafe_allow_html=True)
    st.stop()

fname, pdf_bytes = st.session_state["pdf"]
doc_id = hashlib.sha256(pdf_bytes).hexdigest()[:12]
if st.session_state.get("doc_id") != doc_id:
    st.session_state["doc_id"], st.session_state["log"] = doc_id, {}

with st.status(f"Reviewing **{fname}**…", expanded=False) as status:
    try:
        st.write("Parser agent: extracting steps · Rule agent: safety checks · Retriever: FAISS index · Reviewer: AI")
        res = run_analysis(pdf_bytes, tuple(sorted(profile.items())),
                           hashlib.sha256(api_key.encode()).hexdigest()[:8] if api_key else "",
                           base_url, model, api_key)
        status.update(label=f"Review complete · {res['mode']}", state="complete")
    except ValueError as e:
        status.update(label="Could not read this PDF", state="error")
        st.error(str(e))
        st.stop()

if res["mode"].startswith("Rules only (AI unavailable"):
    st.warning(res["mode"] + " Check your API key / model name.")

# ------------------------------------------------------------------ overview
hot = [s for s in res["steps"] if s["risk"] == "Full attention"]
greet = f"{profile['name']}, here" if profile["name"] else "Here"
st.subheader(f"{greet} is your review of “{res['title']}”")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Readiness score", f"{res['score']}/100", res["grade"], delta_color="off")
m2.metric("Decision", res.get("go_decision", "-"))
m3.metric("Full-attention steps", len(hot))
m4.metric("Findings", len(res["findings"]),
          f"{sum(f['severity'] in ('Critical', 'High') for f in res['findings'])} critical/high", delta_color="inverse")

t1, t2, t3, t4, t5 = st.tabs(["📋 Summary", "🔴 Full attention", "🔎 Findings", "✅ Guided checklist", "📄 Report"])

with t1:
    st.markdown(f"<div class='card'>{res.get('summary', '')}</div>", unsafe_allow_html=True)
    st.markdown("**Pre-job briefing**")
    for line in str(res.get("briefing", "")).split("\n"):
        if line.strip():
            st.markdown(f"- {line.strip().lstrip('-* ')}")
    st.caption(f"{res['pages']} pages · {len(res['steps'])} steps parsed · document ID {res['doc_hash']} · {res['mode']}")

with t2:
    if not hot:
        st.success("No high-risk steps detected.")
    for s in hot:
        a = res["attention"].get(s["num"], {})
        st.markdown(f"""<div class='card hot'><b>Step {s['num']}</b> — {s['text'][:400]}<br>
<small>⚠️ <b>Risk:</b> {a.get('why') or '; '.join(s['reasons'])}</small>
{f"<br><small>👁️ <b>Watch for:</b> {a['watch_for']}</small>" if a.get('watch_for') else ''}</div>""",
                    unsafe_allow_html=True)

with t3:
    sev_filter = st.multiselect("Severity", list(SEV_ICON), default=list(SEV_ICON))
    for f in res["findings"]:
        if f["severity"] not in sev_filter:
            continue
        st.markdown(f"""<div class='card'><span class='sev {f['severity']}'>{f['severity']}</span>
&nbsp;<b>{f['title']}</b> <small>· {f['category']} · {f['source']}</small><br>{f['detail']}<br>
<b style='color:#009688'>Fix:</b> {f['recommendation']}
{f"<br><small>Steps: {', '.join(f['steps'])}</small>" if f['steps'] else ''}</div>""", unsafe_allow_html=True)

with t4:
    st.caption("Steps unlock in order. Full-attention steps need an extra hold-point confirmation.")
    initials = st.text_input("Your initials (recorded with each step)",
                             value="".join(w[0] for w in profile["name"].split()).upper()[:4] or "", max_chars=6)
    log = st.session_state["log"]
    done = len(log)
    st.progress(done / max(len(res["steps"]), 1), text=f"{done} of {len(res['steps'])} steps complete")
    for i, s in enumerate(res["steps"]):
        is_hot = s["risk"] == "Full attention"
        unlocked = i == 0 or res["steps"][i - 1]["num"] in log
        label = f"{'🔴 ' if is_hot else ''}{s['num']}. {s['text'][:180]}"
        if s["num"] in log:
            st.checkbox(label, value=True, disabled=True, key=f"c{i}")
            st.caption(f"✔ {log[s['num']]['time']} · {log[s['num']]['by']}")
            continue
        if not unlocked:
            st.checkbox(label, value=False, disabled=True, key=f"c{i}")
            continue
        hold_ok = True
        if is_hot:
            hold_ok = st.checkbox("Hold point: I confirmed the expected result and the area is safe",
                                  key=f"h{i}")
        if st.checkbox(label, key=f"c{i}", disabled=not (hold_ok and initials)):
            log[s["num"]] = {"time": datetime.now().strftime("%H:%M:%S"), "by": initials or "-"}
            st.rerun()
        if not initials:
            st.info("Enter your initials to start.")
    if log and st.button("Reset checklist"):
        st.session_state["log"] = {}
        st.rerun()

with t5:
    st.write("Download a branded PDF with the score, summary, full-attention steps, findings, "
             "the execution checklist (with your timestamps) and a sign-off block.")
    pdf_out = build_pdf(res, profile, st.session_state["log"])
    st.download_button("⬇️ Download PDF report", pdf_out, type="primary", use_container_width=True,
                       file_name=f"MOP_Safety_Reviewer_Report_{res['doc_hash']}.pdf", mime="application/pdf")

st.markdown(f"<div class='foot'>{APP_NAME} · created by <b>{CREATOR}</b> · "
            "Decision support only. A qualified engineer must approve every MOP.</div>", unsafe_allow_html=True)
