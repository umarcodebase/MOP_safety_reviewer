"""
MOP Safety Reviewer - analysis engine
Created by Umar Shahzad

Pipeline (agentic, 4 stages):
  1. Parser agent    - extracts text + numbered steps from the PDF
  2. Rule agent      - deterministic checks (same input -> same findings, every time)
  3. Retriever       - FAISS index over document chunks; fixed risk queries pull evidence
  4. Reviewer agent  - LLM (temperature 0, JSON mode) reviews evidence per risk category
     Lead agent      - LLM writes the executive summary + "full attention" briefing
Rules form the stable backbone; the LLM adds judgement on top. Without an API key the
app still works in rules-only mode.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field, asdict

import faiss
import numpy as np
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer

# --------------------------------------------------------------------------- data

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
SEVERITY_PENALTY = {"Critical": 15, "High": 10, "Medium": 5, "Low": 2}


@dataclass
class Step:
    num: str
    text: str
    risk: str = "Normal"          # "Full attention" | "Elevated" | "Normal"
    reasons: list = field(default_factory=list)


@dataclass
class Finding:
    category: str
    severity: str
    title: str
    detail: str
    recommendation: str
    steps: list = field(default_factory=list)
    source: str = "Rule"          # "Rule" | "AI"


# ---------------------------------------------------------------- 1. parser agent

STEP_RE = re.compile(r"^\s*(?:step\s*)?(\d{1,3}(?:\.\d{1,2})*)\s*[\.\):\-]\s+(.+)", re.I)


def extract_text(pdf_bytes: bytes, max_pages: int) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    n = len(reader.pages)
    if n > max_pages:
        raise ValueError(f"PDF has {n} pages; the limit is {max_pages}.")
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    text = re.sub(r"[ \t]+", " ", text)
    if len(text.strip()) < 80:
        raise ValueError("No readable text found. Scanned/image PDFs are not supported - "
                         "please upload a text-based PDF.")
    return text, n


def parse_steps(text: str) -> list[Step]:
    steps, cur = [], None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = STEP_RE.match(line)
        if m and len(m.group(2)) > 3:
            cur = Step(m.group(1), m.group(2))
            steps.append(cur)
        elif cur and not re.match(r"^[A-Z][A-Z \-/&]{3,}$", line):  # continuation, not a heading
            cur.text += " " + line
    if len(steps) < 3:  # fallback: sentence split
        sents = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if len(s.strip()) > 15]
        steps = [Step(str(i + 1), s) for i, s in enumerate(sents[:150])]
    return steps


# ------------------------------------------------------------------ 2. rule agent

def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.I) is not None


HIGH_RISK_ACTIONS = {
    r"\b(open|close|trip|rack(ed|ing)? (in|out))\b.*\b(breaker|switch|cb)\b|\b(breaker|cb)\b.*\b(open|close|trip)":
        "Switching a breaker changes the live power path",
    r"\bbypass\b": "Bypass mode removes UPS protection from the load",
    r"\btransfer\b": "Load transfer can drop the load if sync/phase is wrong",
    r"\b(de-?energi[sz]e|isolate|isolation|shut ?down|switch off|power off|take .* offline)\b":
        "Removes equipment from service - redundancy is reduced",
    r"\b(re-?energi[sz]e|energi[sz]e|power on|restore power)\b": "Re-energising is a high-energy step",
    r"\bgenerator|genset\b": "Generator operation affects backup power availability",
    r"\bbatter(y|ies)|string\b": "Battery work: DC arc-flash and hydrogen hazards",
    r"\b(switchgear|busway|busbar|mv|medium voltage|transformer|ats|sts)\b": "High-energy electrical equipment",
    r"\b(drain|refill|coolant|cdu|chiller|valve)\b": "Fluid work: leak / loss-of-cooling risk",
    r"\b(lock ?out|loto|tag ?out)\b": "Energy isolation point - must be verified",
}

VAGUE_TERMS = [r"\bas (needed|required|necessary)\b", r"\bif (necessary|needed|required)\b",
               r"\bappropriate(ly)?\b", r"\betc\.?", r"\bapprox(imately|\.)?\b", r"\bsome\b",
               r"\bquickly\b", r"\bcarefully\b", r"\bnormal(ly)?\b", r"\bproper(ly)?\b", r"\bseveral\b",
               r"\bsoon\b", r"\bmake sure\b"]
GENERIC_EQUIP = r"\bthe (breaker|valve|switch|unit|panel|pump|ups|pdu|module|generator|feeder)\b"
EQUIP_TAG = r"\b[A-Z]{2,5}(?:-[A-Z0-9]{1,3}|\d{1,3}[A-Z]?)(?:[-.]\d{1,3})?\b"
ELECTRICAL = r"\b(breaker|switchgear|ups|pdu|ats|sts|busway|panel|feeder|energi[sz]|voltage|kv|battery)\b"


def classify_steps(steps: list[Step]) -> None:
    for s in steps:
        for pat, why in HIGH_RISK_ACTIONS.items():
            if _has(s.text, pat):
                s.reasons.append(why)
        s.reasons = list(dict.fromkeys(s.reasons))
        if len(s.reasons) >= 2 or any(k in " ".join(s.reasons) for k in ("Bypass", "transfer", "breaker", "Re-energising", "Removes equipment")):
            s.risk = "Full attention"
        elif s.reasons:
            s.risk = "Elevated"


def rule_checks(text: str, steps: list[Step], context: str) -> list[Finding]:
    f: list[Finding] = []
    full = text + "\n" + (context or "")
    electrical = _has(text, ELECTRICAL)
    removes_redundancy = [s.num for s in steps if _has(
        s.text, r"\b(bypass|isolate|de-?energi[sz]e|shut ?down|switch off|take .* offline|out of service|open .*breaker)\b")]

    if not _has(text, r"back[- ]?out|roll[- ]?back|revert|restore to (the )?(original|normal|initial)|contingency|reversal"):
        f.append(Finding("Back-out plan", "Critical", "No back-out / rollback plan",
                         "The MOP never says how to return the system to a safe state if a step fails.",
                         "Add a back-out section: the trigger conditions to abort, and step-by-step reversal to the original configuration."))
    if electrical and not _has(text, r"lock ?-?out|\bloto\b|tag ?-?out"):
        f.append(Finding("Energy isolation", "Critical", "No Lockout/Tagout (LOTO)",
                         "Electrical isolation is performed but no lockout/tagout is specified.",
                         "Add LOTO steps naming each isolation point, lock owner and tag ID."))
    if electrical and not _has(text, r"zero (energy|voltage)|absence of voltage|live[- ]dead[- ]live|test before touch|verify .*de-?energi[sz]ed"):
        f.append(Finding("Energy isolation", "High", "No zero-energy verification",
                         "There is no step to prove the equipment is dead before work starts.",
                         "Add 'test before touch' with a rated meter (live-dead-live) and record the reading."))
    if electrical and not _has(text, r"\bppe\b|arc[- ]?flash|arc rated|insulat(ed|ing) gloves|face ?shield"):
        f.append(Finding("Safety", "High", "PPE / arc-flash category not stated",
                         "Electrical work is listed without the required PPE or arc-flash category.",
                         "State the arc-flash PPE category (per the site study / NFPA 70E) for each energised task."))
    if removes_redundancy and not _has(full, r"n\+1|n\+2|2n|redundan|single point|risk window|reduced resilience"):
        f.append(Finding("Redundancy", "High", "Loss of redundancy not acknowledged",
                         "These steps take equipment out of service, but the MOP never states the resulting redundancy level or the risk window.",
                         "State the redundancy before/during/after (e.g. N+1 -> N), the maximum allowed duration, and who approved operating at reduced redundancy.",
                         removes_redundancy))
    if not _has(text, r"notif|inform|bms|noc|soc|control room|customer|stakeholder|change (request|ticket|record)|\bcr\b"):
        f.append(Finding("Communication", "Medium", "No notification / communication steps",
                         "No step informs the BMS/NOC operator, customers or the change board before and after work.",
                         "Add notify-before-start and notify-on-completion steps with named roles."))
    if not _has(text, r"approv|sign[- ]?off|authori[sz]ed by|reviewed by"):
        f.append(Finding("Governance", "Medium", "No approval / sign-off block",
                         "The document has no author, reviewer or approver.",
                         "Add an approval block (author, reviewer, approver, date, version)."))
    if not _has(text, r"abort|stop work|halt|cease|emergency|escalat"):
        f.append(Finding("Back-out plan", "High", "No abort / stop-work criteria",
                         "Technicians are not told when to stop (e.g. unexpected alarm, wrong reading).",
                         "Add explicit stop-work triggers and the escalation contact."))
    if not _has(text, r"duration|minutes|\bmins?\b|hours|\bhrs?\b|window|start time|end time"):
        f.append(Finding("Planning", "Low", "No time window / durations",
                         "No maintenance window or step durations are given.",
                         "Add the approved window and expected duration of the reduced-redundancy period."))

    verify_re = r"verify|confirm|check that|ensure .* (reads|shows|is)|expected|should (read|show|indicate)|record"
    action_steps = [s for s in steps if s.risk != "Normal"]
    unverified = [s.num for s in action_steps if not _has(s.text, verify_re)]
    if action_steps and len(unverified) / len(action_steps) > 0.5:
        f.append(Finding("Verification", "Medium", "High-risk steps without an expected result",
                         f"{len(unverified)} of {len(action_steps)} risky steps do not state what the technician should see afterwards.",
                         "After every switching step, add the expected indication (alarm, lamp, meter value) as a hold point.",
                         unverified[:15]))

    vague = {}
    for s in steps:
        hits = [re.search(p, s.text, re.I).group(0) for p in VAGUE_TERMS if _has(s.text, p)]
        if _has(s.text, GENERIC_EQUIP) and not re.search(EQUIP_TAG, s.text):
            hits.append(re.search(GENERIC_EQUIP, s.text, re.I).group(0))
        if hits:
            vague[s.num] = sorted(set(h.lower() for h in hits))
    if vague:
        refs = list(vague)[:15]
        sample = "; ".join(f"step {k}: '{', '.join(v)}'" for k, v in list(vague.items())[:5])
        f.append(Finding("Clarity", "Medium" if len(vague) > 2 else "Low", "Ambiguous wording",
                         f"Vague terms or unnamed equipment found ({sample}).",
                         "Replace vague words with exact values, and name every device by its asset tag (e.g. 'UPS-A1 output breaker CB-12').",
                         refs))
    return f


# ------------------------------------------------------------------ 3. retriever

RISK_QUERIES = {
    "Back-out plan": "back out rollback revert restore original configuration abort contingency failure",
    "Energy isolation": "lockout tagout isolate de-energize zero energy verify voltage test before touch",
    "Redundancy": "redundancy N+1 bypass transfer load single point of failure take offline out of service",
    "Safety": "PPE arc flash hazard gloves face shield qualified person permit to work",
    "Communication": "notify inform BMS operator NOC customer change request approval escalation",
    "Verification": "verify confirm expected reading indication alarm record value",
}


class DocIndex:
    """Run-time FAISS index. Vectors are TF-IDF (deterministic, no extra API, no GPU)."""

    def __init__(self, text: str, size: int = 700, overlap: int = 120):
        self.chunks = [text[i:i + size] for i in range(0, max(len(text) - overlap, 1), size - overlap)]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        mat = self.vec.fit_transform(self.chunks).astype(np.float32).toarray()
        faiss.normalize_L2(mat)
        self.index = faiss.IndexFlatIP(mat.shape[1])
        self.index.add(mat)

    def search(self, query: str, k: int = 3) -> list[str]:
        q = self.vec.transform([query]).astype(np.float32).toarray()
        if not q.any():
            return []
        faiss.normalize_L2(q)
        scores, ids = self.index.search(q, min(k, len(self.chunks)))
        return [self.chunks[i] for s, i in zip(scores[0], ids[0]) if i >= 0 and s > 0.02]


# -------------------------------------------------------------- 4. LLM agents

PROVIDERS = {
    "Groq (free)": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "xAI Grok": ("https://api.x.ai/v1", "grok-3-mini"),
}

REVIEW_SYSTEM = """You are a senior data center critical-facilities engineer (electrical + mechanical)
reviewing a Method of Procedure (MOP). Be precise, conservative and practical. Only report issues that
are supported by the evidence or clearly missing from it. Never invent equipment names.
Return ONLY valid JSON."""

REVIEW_TASK = """Reviewer context: {context}

Deterministic checks ALREADY found these issues (do not repeat them):
{rule_titles}

Evidence retrieved from the MOP per risk category:
{evidence}

Numbered steps flagged as risky:
{risky_steps}

Task: add up to 6 ADDITIONAL, non-duplicate findings a senior engineer would raise (e.g. wrong step
order, missing hold point, unsafe sequence, missing pre-checks, missing load verification).
JSON schema:
{{"findings":[{{"category":"<one of: Back-out plan, Energy isolation, Redundancy, Safety, Communication, Verification, Clarity, Sequence, Planning>",
"severity":"Critical|High|Medium|Low","title":"<max 8 words>","detail":"<1-2 sentences>",
"recommendation":"<1 sentence, actionable>","steps":["<step numbers>"]}}],
"attention":[{{"step":"<step number>","why":"<one sentence: what can go wrong>","watch_for":"<what the technician must observe>"}}]}}
"attention" = the top risky steps (max 8) that need full attention."""

SUMMARY_TASK = """Write for {reader} ({level}). MOP: "{title}". Score {score}/100 ({grade}).
Findings: {findings}
Return JSON: {{"summary":"<4-5 sentence executive summary: is it safe to execute as written, top 3 risks, what to fix first>",
"go_decision":"Go|Go with fixes|No-go","briefing":"<pre-job briefing, 4 short bullet lines separated by \\n, addressed to the technician>"}}"""


def _llm_json(client, model: str, system: str, user: str) -> dict:
    kw = dict(model=model, temperature=0, max_tokens=2500,
              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        r = client.chat.completions.create(response_format={"type": "json_object"}, seed=42, **kw)
    except Exception:  # some providers reject seed/json mode - retry plain
        r = client.chat.completions.create(**kw)
    raw = r.choices[0].message.content or "{}"
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


def ai_review(client, model, idx: DocIndex, steps, rule_findings, context) -> tuple[list[Finding], dict]:
    evidence = "\n".join(f"[{cat}]\n" + "\n...\n".join(idx.search(q, 2)) for cat, q in RISK_QUERIES.items())
    risky = "\n".join(f"{s.num}. {s.text[:220]}" for s in steps if s.risk != "Normal")[:6000]
    data = _llm_json(client, model, REVIEW_SYSTEM, REVIEW_TASK.format(
        context=context or "none", rule_titles="\n".join(f"- {x.title}" for x in rule_findings) or "- none",
        evidence=evidence[:9000], risky_steps=risky or "none"))
    known = {x.title.lower() for x in rule_findings}
    out = []
    for d in data.get("findings", [])[:6]:
        sev = str(d.get("severity", "Medium")).title()
        title = str(d.get("title", "")).strip()
        if not title or title.lower() in known or sev not in SEVERITY_ORDER:
            continue
        out.append(Finding(str(d.get("category", "Review")), sev, title, str(d.get("detail", "")),
                           str(d.get("recommendation", "")), [str(x) for x in d.get("steps", [])][:10], "AI"))
    attention = {str(a.get("step")): a for a in data.get("attention", []) if a.get("step")}
    return out, attention


def ai_summary(client, model, profile: dict, title, score, grade, findings) -> dict:
    fl = "; ".join(f"[{x.severity}] {x.title}" for x in findings)
    return _llm_json(client, model, REVIEW_SYSTEM, SUMMARY_TASK.format(
        reader=profile.get("name") or "the reviewer", level=profile.get("role", "engineer"),
        title=title, score=score, grade=grade, findings=fl))


# ------------------------------------------------------------------ orchestrator

def score_findings(findings: list[Finding]) -> tuple[int, str]:
    s = max(0, 100 - sum(SEVERITY_PENALTY[x.severity] for x in findings))
    grade = "Ready" if s >= 85 else "Needs revision" if s >= 60 else "Not safe to execute"
    return s, grade


def fallback_summary(score, grade, findings) -> dict:
    crit = [x.title for x in findings if x.severity in ("Critical", "High")][:3]
    go = "Go" if score >= 85 else "Go with fixes" if score >= 60 else "No-go"
    return {"summary": f"Rules-only review. Score {score}/100 - {grade}. "
                       + (f"Fix first: {', '.join(crit)}." if crit else "No critical gaps detected."),
            "go_decision": go,
            "briefing": "Read the full MOP before starting\nStop at every Full-attention step and confirm the expected result\n"
                        "Never skip or re-order steps\nIf anything is unexpected: STOP, make safe, escalate"}


def analyze(pdf_bytes: bytes, profile: dict, client=None, model: str = "", max_pages: int = 40) -> dict:
    text, pages = extract_text(pdf_bytes, max_pages)
    steps = parse_steps(text)
    classify_steps(steps)
    findings = rule_checks(text, steps, profile.get("context", ""))
    idx = DocIndex(text)
    attention, mode = {}, "Rules only"
    if client:
        try:
            extra, attention = ai_review(client, model, idx, steps, findings, profile.get("context", ""))
            findings += extra
            mode = f"Rules + AI ({model})"
        except Exception as e:
            mode = f"Rules only (AI unavailable: {str(e)[:80]})"
    for s in steps:  # AI can only escalate, never downgrade
        if s.num in attention and s.risk != "Full attention":
            s.risk = "Full attention"
            s.reasons.append("Flagged by AI reviewer")
    findings.sort(key=lambda x: (SEVERITY_ORDER[x.severity], x.category))
    score, grade = score_findings(findings)
    title = next((l.strip() for l in text.splitlines() if len(l.strip()) > 8), "Untitled MOP")[:90]
    summ = {}
    if client and mode.startswith("Rules +"):
        try:
            summ = ai_summary(client, model, profile, title, score, grade, findings)
        except Exception:
            summ = {}
    summ = {**fallback_summary(score, grade, findings), **{k: v for k, v in summ.items() if v}}
    return {
        "doc_hash": hashlib.sha256(pdf_bytes).hexdigest()[:12], "title": title, "pages": pages,
        "steps": [asdict(s) for s in steps], "findings": [asdict(x) for x in findings],
        "attention": attention, "score": score, "grade": grade, "mode": mode, **summ,
    }
