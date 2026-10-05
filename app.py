"""
MOP Safety Reviewer - AI-assisted Method of Procedure safety review for data center maintenance.
Created by Umar Shahzad.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from html import escape
from pathlib import Path

import streamlit as st
from openai import OpenAI

from mop_engine import PROVIDERS, analyze
from report import APP_NAME, CREATOR, build_pdf
from theme import css, score_ring

MAX_MB, MAX_PAGES = 10, 40
SAMPLE = Path(__file__).parent / "samples" / "sample_mop_ups_bypass.pdf"
DECISION_CLASS = {"Go": "go", "Go with fixes": "fixes", "No-go": "nogo"}

st.set_page_config(page_title=f"{APP_NAME} · by {CREATOR}", page_icon="🛡️",
                   layout="centered", initial_sidebar_state="collapsed")
st.markdown(css(), unsafe_allow_html=True)


# ------------------------------------------------------------- AI engine (hidden)
def _engine():
    """Key comes only from app secrets. Users never see provider, model or key."""
    try:
        if st.secrets.get("GROQ_API_KEY"):
            url, model = PROVIDERS["Groq (free)"]
            return st.secrets["GROQ_API_KEY"], url, st.secrets.get("GROQ_MODEL", model)
        if st.secrets.get("XAI_API_KEY"):
            url, model = PROVIDERS["xAI Grok"]
            return st.secrets["XAI_API_KEY"], url, st.secrets.get("XAI_MODEL", model)
    except Exception:
        pass
    return "", "", ""


API_KEY, BASE_URL, MODEL = _engine()


@st.cache_data(show_spinner=False, max_entries=32)
def run_analysis(pdf_bytes: bytes, profile_items: tuple, base_url: str, model: str, _key: str):
    """Cached: same document + same details -> identical result."""
    client = OpenAI(api_key=_key, base_url=base_url, timeout=60) if _key else None
    return analyze(pdf_bytes, dict(profile_items), client, model, MAX_PAGES)


# ------------------------------------------------------------------ header
st.markdown(f"""<div class="nav"><div class="brand"><div class="logo">🛡</div>{APP_NAME}</div>
<div class="by">Created by <b>{CREATOR}</b></div></div>
<div class="hero"><div class="eyebrow">Data center maintenance safety</div>
<h1>Catch the mistake on paper,<br><span class="grad">before it happens on the floor.</span></h1>
<p class="lead">Upload a Method of Procedure (MOP). In seconds you get a readiness score, the steps that need
full attention, every safety gap, and a report you can share.</p>
<div class="stat">⚡ <span>Failure to follow procedures is the <b>#1 driver</b> of human-error outages (Uptime Institute, 2026)</span></div>
</div>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ input
up = st.file_uploader(f"Upload your MOP (text-based PDF, up to {MAX_MB} MB / {MAX_PAGES} pages)", type=["pdf"])
c1, c2 = st.columns([1, 2])
with c1:
    if st.button("Try a sample MOP", use_container_width=True, disabled=not SAMPLE.exists()):
        st.session_state["pdf"] = ("sample_mop_ups_bypass.pdf", SAMPLE.read_bytes())
with c2:
    st.markdown("<div class='meta' style='padding-top:.55rem'>Files are processed in memory and never stored. "
                "Please use non-confidential documents.</div>", unsafe_allow_html=True)

with st.expander("Add details to your report (optional)"):
    a, b = st.columns(2)
    name = a.text_input("Your name")
    role = b.selectbox("Your role", ["Not specified", "Critical facilities engineer", "Data center technician",
                                     "Shift lead / supervisor", "Contractor", "Student / learner"])
    site = a.text_input("Site or facility")
    context = b.text_area("Equipment and redundancy notes", height=96,
                          help="For example, which UPS units feed which PDUs and how redundant they are.")
profile = {"name": name.strip(), "role": "" if role == "Not specified" else role,
           "site": site.strip(), "context": context.strip()}

if up is not None:
    if up.size > MAX_MB * 1024 * 1024:
        st.error(f"This file is {up.size / 1e6:.1f} MB. The limit is {MAX_MB} MB.")
        st.stop()
    st.session_state["pdf"] = (up.name, up.getvalue())

if "pdf" not in st.session_state:
    st.write("")
    cols = st.columns(3)
    for col, (n, t, d) in zip(cols, [
        ("01", "Upload", "Any MOP, SOP or EOP as a PDF."),
        ("02", "Review", "Safety rules and an AI reviewer flag gaps and high-risk steps."),
        ("03", "Act", "Fix what's flagged, then execute with a guided checklist and export a report.")]):
        col.markdown(f"<div class='card'><div class='n'>{n}</div><h3>{t}</h3><div class='meta'>{d}</div></div>",
                     unsafe_allow_html=True)
    st.markdown(f"<div class='foot'>{APP_NAME} · Created by {CREATOR}</div>", unsafe_allow_html=True)
    st.stop()

# ------------------------------------------------------------------ analysis
fname, pdf_bytes = st.session_state["pdf"]
doc_id = hashlib.sha256(pdf_bytes).hexdigest()[:12]
if st.session_state.get("doc_id") != doc_id:
    st.session_state["doc_id"], st.session_state["log"] = doc_id, {}

with st.spinner(f"Reviewing {fname}…"):
    try:
        res = run_analysis(pdf_bytes, tuple(sorted(profile.items())), BASE_URL, MODEL, API_KEY)
    except ValueError as e:
        st.error(str(e))
        st.stop()

hot = [s for s in res["steps"] if s["risk"] == "Full attention"]
decision = res.get("go_decision", "No-go")
crit_high = sum(f["severity"] in ("Critical", "High") for f in res["findings"])
greet = f"{escape(profile['name'])}, here's" if profile["name"] else "Here's"

st.markdown(f"""<div class="card"><div class="meta">{greet} the review of</div>
<h3 style="font-size:1.45rem;margin:.2rem 0 1rem">{escape(res['title'])}</h3>
<div class="scorebox">{score_ring(res['score'])}
<div style="flex:1;min-width:260px"><span class="chip {DECISION_CLASS.get(decision, 'nogo')}">{decision}</span>
&nbsp;<span class="meta">{res['grade']}</span>
<div class="kpis" style="margin-top:14px">
<div class="kpi"><div class="v">{len(hot)}</div><div class="l">Full-attention steps</div></div>
<div class="kpi"><div class="v">{len(res['findings'])}</div><div class="l">Findings</div></div>
<div class="kpi"><div class="v">{crit_high}</div><div class="l">Critical / high</div></div>
</div></div></div></div>""", unsafe_allow_html=True)

t1, t2, t3, t4, t5 = st.tabs(["Summary", "Full attention", "Findings", "Guided checklist", "Report"])

with t1:
    st.markdown(f"<div class='card'><h3>Executive summary</h3>{escape(res.get('summary', ''))}</div>",
                unsafe_allow_html=True)
    lines = "".join(f"<li>{escape(l.strip().lstrip('-* '))}</li>"
                    for l in str(res.get("briefing", "")).split("\n") if l.strip())
    st.markdown(f"<div class='card'><h3>Pre-job briefing</h3><ul>{lines}</ul></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='meta'>{res['pages']} page(s) · {len(res['steps'])} steps · document ID {res['doc_hash']}</div>",
                unsafe_allow_html=True)

with t2:
    if not hot:
        st.success("No high-risk steps detected.")
    for s in hot:
        a = res["attention"].get(s["num"], {})
        watch = f"<br><span class='meta'>👁 <b>Watch for:</b> {escape(a['watch_for'])}</span>" if a.get("watch_for") else ""
        st.markdown(f"""<div class='card hot'><b>Step {escape(s['num'])}</b> · {escape(s['text'][:400])}<br>
<span class='meta'>⚠ <b>Risk:</b> {escape(a.get('why') or '; '.join(s['reasons']))}</span>{watch}</div>""",
                    unsafe_allow_html=True)

with t3:
    for f in res["findings"]:
        steps = f"<br><span class='meta'>Steps: {escape(', '.join(f['steps']))}</span>" if f["steps"] else ""
        st.markdown(f"""<div class='card'><span class='sev {f['severity']}'>{f['severity']}</span>
&nbsp;<b>{escape(f['title'])}</b> <span class='meta'>· {escape(f['category'])}</span><br>{escape(f['detail'])}<br>
<span class='fix'>Fix:</span> {escape(f['recommendation'])}{steps}</div>""", unsafe_allow_html=True)

with t4:
    if decision == "No-go":
        st.markdown("""<div class='card hot'><h3>🔒 Checklist locked</h3>This MOP is <b>not safe to execute as written</b>.
Fix the critical and high findings, upload the revised MOP, and the guided checklist unlocks automatically.</div>""",
                    unsafe_allow_html=True)
    else:
        if decision == "Go with fixes":
            st.warning("Approved with fixes: apply the findings before or during execution.")
        st.caption("Steps unlock in order. Full-attention steps need a hold-point confirmation.")
        initials = st.text_input("Your initials (recorded with each step)",
                                 value="".join(w[0] for w in profile["name"].split()).upper()[:4], max_chars=6)
        log = st.session_state["log"]
        st.progress(len(log) / max(len(res["steps"]), 1), text=f"{len(log)} of {len(res['steps'])} steps complete")
        for i, s in enumerate(res["steps"]):
            is_hot = s["risk"] == "Full attention"
            label = f"{'🔴 ' if is_hot else ''}{s['num']}. {s['text'][:180]}"
            if s["num"] in log:
                st.checkbox(label, value=True, disabled=True, key=f"c{i}")
                st.caption(f"✔ {log[s['num']]['time']} · {log[s['num']]['by']}")
                continue
            if i > 0 and res["steps"][i - 1]["num"] not in log:
                st.checkbox(label, value=False, disabled=True, key=f"c{i}")
                continue
            hold_ok = st.checkbox("Hold point: expected result confirmed and area is safe", key=f"h{i}") if is_hot else True
            if not initials:
                st.info("Enter your initials to start.")
            if st.checkbox(label, key=f"c{i}", disabled=not (hold_ok and initials)):
                log[s["num"]] = {"time": datetime.now().strftime("%H:%M:%S"), "by": initials}
                st.rerun()
        if log and st.button("Reset checklist"):
            st.session_state["log"] = {}
            st.rerun()

with t5:
    st.markdown("<div class='card'><h3>Download the report</h3>Score, summary, full-attention steps, findings"
                + (", the execution checklist" if decision != "No-go" else "")
                + " and a sign-off block, in one branded PDF.</div>", unsafe_allow_html=True)
    st.download_button("Download PDF report", build_pdf(res, profile, st.session_state["log"]),
                       use_container_width=True, mime="application/pdf",
                       file_name=f"MOP_Safety_Reviewer_Report_{res['doc_hash']}.pdf")

st.markdown(f"<div class='foot'>{APP_NAME} · Created by <b>{CREATOR}</b><br>"
            "Decision support only. A qualified engineer must approve every MOP.</div>", unsafe_allow_html=True)
