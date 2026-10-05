"""MOP Safety Reviewer - visual theme. Created by Umar Shahzad.

Background: if assets/bg.jpg exists it is used (any data center photo you own or that is
free to use). Otherwise an original, code-drawn server-hall illustration is used, so the
app never depends on an external image link.
"""
from __future__ import annotations

import base64
import random
from pathlib import Path

BG_PHOTO = Path(__file__).parent / "assets" / "bg.jpg"


def _rack_row(rnd, y, h, w, n, gap, opacity, led_scale, x0=0):
    parts = []
    for i in range(n):
        x = x0 + i * (w + gap)
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="#0f1c2e" '
                     f'stroke="#2a4d6b" stroke-width="1.5" opacity="{opacity}"/>')
        units = int(h // (9 * led_scale))
        for u in range(2, units - 1):
            uy = y + u * 9 * led_scale
            parts.append(f'<line x1="{x + 6}" y1="{uy}" x2="{x + w - 6}" y2="{uy}" stroke="#16293d" '
                         f'stroke-width="{led_scale}" opacity="{opacity}"/>')
            if rnd.random() < 0.55:
                c = rnd.choices(["#2dd4bf", "#22c55e", "#38bdf8", "#f59e0b"], [6, 4, 3, 0.4])[0]
                for k in range(rnd.randint(1, 3)):
                    parts.append(f'<circle cx="{x + 12 + k * 7 * led_scale}" cy="{uy + 4 * led_scale}" '
                                 f'r="{1.4 * led_scale}" fill="{c}" opacity="{opacity * rnd.uniform(.55, 1)}"/>')
    return parts


def server_hall_svg() -> str:
    rnd = random.Random(7)
    p = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">',
         '<defs><radialGradient id="g" cx="50%" cy="85%" r="70%"><stop offset="0" stop-color="#0f3b4a"/>'
         '<stop offset="1" stop-color="#050b14"/></radialGradient>'
         '<linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2dd4bf" stop-opacity=".18"/>'
         '<stop offset="1" stop-color="#2dd4bf" stop-opacity="0"/></linearGradient></defs>',
         '<rect width="1600" height="900" fill="url(#g)"/>']
    for i in range(9):  # ceiling cable trays / light strips
        p.append(f'<rect x="{80 + i * 170}" y="40" width="120" height="4" rx="2" fill="#7dd3fc" opacity=".25"/>')
    p += _rack_row(rnd, 190, 380, 62, 22, 10, .6, .8, x0=10)      # back row
    p += _rack_row(rnd, 300, 520, 118, 12, 16, .9, 1.25, x0=-30)    # front row
    p.append('<rect x="0" y="820" width="1600" height="80" fill="url(#f)"/>')
    for i in range(0, 1600, 80):  # raised-floor tiles
        p.append(f'<line x1="{i}" y1="820" x2="{i - 40}" y2="900" stroke="#1e3a52" stroke-width="1"/>')
    p.append("</svg>")
    return "data:image/svg+xml;base64," + base64.b64encode("".join(p).encode()).decode()


def background_uri() -> str:
    if BG_PHOTO.exists():
        return "data:image/jpeg;base64," + base64.b64encode(BG_PHOTO.read_bytes()).decode()
    return server_hall_svg()


def css() -> str:
    bg = background_uri()
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
:root {{
  --display:'Space Grotesk','Inter',system-ui,-apple-system,'Segoe UI',sans-serif; --ink:#e6edf5; --muted:#94a3b8; --line:rgba(148,163,184,.18);
  --glass:rgba(10,20,34,.72); --accent:#2dd4bf; --accent2:#38bdf8;
  --crit:#ef4444; --high:#f97316; --med:#eab308; --low:#22c55e;
}}
html, body, [class*="css"], .stMarkdown, p, li, label, input, textarea {{ font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif; }}
.stApp {{
  background: linear-gradient(180deg, rgba(5,11,20,.25) 0%, rgba(5,11,20,.62) 45%, rgba(5,11,20,.9) 100%),
              url("{bg}") center top / cover fixed no-repeat;
  color:var(--ink);
}}
[data-testid="stSidebar"], [data-testid="collapsedControl"], header[data-testid="stHeader"],
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display:none !important; }}
.block-container {{ max-width:1080px; padding:1.2rem 1.4rem 3rem; }}
p, li {{ font-size:1.05rem; line-height:1.65; }}

/* nav */
.nav {{ display:flex; align-items:center; justify-content:space-between; padding:10px 0 18px;
        border-bottom:1px solid var(--line); margin-bottom:46px; }}
.brand {{ display:flex; gap:12px; align-items:center; font-family:var(--display); font-weight:700;
          font-size:1.25rem; letter-spacing:-.01em; }}
.logo {{ width:34px; height:34px; border-radius:9px; display:grid; place-items:center;
         background:linear-gradient(135deg,var(--accent),var(--accent2)); color:#04131a; font-size:1.05rem; }}
.by {{ color:var(--muted); font-size:.92rem; }}
.by b {{ color:var(--ink); font-weight:600; }}

/* hero */
.eyebrow {{ color:var(--accent); font-weight:600; letter-spacing:.14em; text-transform:uppercase; font-size:.8rem; }}
.hero h1 {{ font-family:var(--display); font-size:clamp(2.2rem,5vw,3.6rem); line-height:1.05;
            letter-spacing:-.025em; margin:.5rem 0 1rem; color:#fff !important; }}
.hero .grad {{ background:linear-gradient(90deg,var(--accent),var(--accent2)); -webkit-background-clip:text;
                 background-clip:text; color:transparent; }}
.hero p.lead {{ font-size:1.2rem; color:#cbd5e1; max-width:680px; }}
.stat {{ display:inline-flex; gap:10px; align-items:center; margin:18px 0 30px; padding:8px 14px;
         border:1px solid var(--line); border-radius:999px; background:var(--glass); font-size:.9rem; color:#cbd5e1; }}
.stat b {{ color:var(--accent); }}

/* cards */
.card {{ background:var(--glass); backdrop-filter:blur(10px); border:1px solid var(--line);
         border-radius:16px; padding:20px 22px; margin-bottom:14px; }}
.card h3 {{ font-family:var(--display); font-size:1.15rem; margin:0 0 6px; color:#fff; }}
.card .n {{ font-family:var(--display); color:var(--accent); font-size:.85rem; font-weight:700; letter-spacing:.1em; }}
.hot {{ border-left:4px solid var(--crit); }}
.sev {{ font-weight:700; font-size:.72rem; letter-spacing:.06em; text-transform:uppercase;
        padding:3px 10px; border-radius:999px; color:#0b1220; }}
.Critical {{ background:var(--crit); color:#fff; }} .High {{ background:var(--high); }}
.Medium {{ background:var(--med); }} .Low {{ background:var(--low); }}
.fix {{ color:var(--accent); font-weight:600; }}
.meta {{ color:var(--muted); font-size:.88rem; }}

/* score */
.scorebox {{ display:flex; gap:28px; align-items:center; flex-wrap:wrap; }}
.kpis {{ display:grid; grid-template-columns:repeat(3,minmax(120px,1fr)); gap:12px; flex:1; }}
.kpi {{ background:rgba(255,255,255,.03); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.kpi .v {{ font-family:var(--display); font-size:1.7rem; font-weight:700; color:#fff; }}
.kpi .l {{ color:#b6c2d1; font-size:.82rem; text-transform:uppercase; letter-spacing:.08em; }}
.chip {{ display:inline-block; padding:6px 14px; border-radius:999px; font-weight:700; font-size:.9rem; }}
.go {{ background:rgba(34,197,94,.15); color:#4ade80; border:1px solid rgba(34,197,94,.4); }}
.fixes {{ background:rgba(249,115,22,.15); color:#fb923c; border:1px solid rgba(249,115,22,.4); }}
.nogo {{ background:rgba(239,68,68,.15); color:#f87171; border:1px solid rgba(239,68,68,.45); }}

/* streamlit widgets */
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid var(--line); }}
.stTabs [data-baseweb="tab"] {{ font-family:var(--display); font-size:1.02rem; padding:10px 16px; }}
[data-testid="stFileUploader"] section {{ background:rgba(255,255,255,.03); border:1.5px dashed rgba(45,212,191,.45);
                                          border-radius:14px; padding:22px; }}
.stButton button, .stDownloadButton button {{ border-radius:10px; font-weight:600; padding:.6rem 1.1rem; }}
.stDownloadButton button {{ background:linear-gradient(90deg,var(--accent),var(--accent2)); color:#04131a; border:0; }}
[data-testid="stExpander"] {{ background:var(--glass); border:1px solid var(--line); border-radius:14px; }}
.foot {{ text-align:center; color:var(--muted); font-size:.85rem; margin-top:50px; padding-top:18px;
         border-top:1px solid var(--line); }}

/* ---- force readable colours even if the Streamlit theme file is missing (light mode) ---- */
.stApp, .stApp p, .stApp li, .stApp span, .stApp label, .stApp div, .stApp small,
[data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] p,
[data-testid="stCaptionContainer"], [data-testid="stCheckbox"] label p {{ color:var(--ink); }}
.meta, .meta *, .by, .kpi .l, [data-testid="stCaptionContainer"] p {{ color:#b6c2d1 !important; }}
.eyebrow, .card .n, .fix {{ color:var(--accent) !important; }}
.hero h1 {{ color:#fff !important; }}
.grad {{ background:linear-gradient(90deg,var(--accent),var(--accent2)) !important; -webkit-background-clip:text !important;
         background-clip:text !important; color:transparent !important; -webkit-text-fill-color:transparent !important; }}
[data-testid="stWidgetLabel"] p {{ font-size:1rem !important; font-weight:600 !important; color:#fff !important; }}
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section {{ background:rgba(10,20,34,.85) !important; }}
[data-testid="stFileUploaderDropzone"] *, [data-testid="stFileUploaderFile"] * {{ color:#e6edf5 !important; }}
[data-testid="stFileUploaderDropzone"] button, .stButton button {{ background:#0e1a2b !important; color:#fff !important;
        border:1px solid rgba(45,212,191,.55) !important; }}
[data-testid="stFileUploaderDropzone"] button:hover, .stButton button:hover {{ background:#12263a !important; border-color:var(--accent) !important; }}
.stDownloadButton button, .stDownloadButton button * {{ color:#04131a !important; }}
.stTabs [data-baseweb="tab"] p, .stTabs [data-baseweb="tab"] {{ color:#cbd5e1 !important; font-weight:600; }}
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] p {{ color:var(--accent) !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs .react-aria-SelectionIndicator {{ background:var(--accent) !important; }}
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary * {{ color:#fff !important; }}
[data-testid="stExpander"] details {{ background:transparent !important; }}
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {{ background:#0e1a2b !important; color:#fff !important;
        border:1px solid rgba(148,163,184,.35) !important; }}
[data-baseweb="select"] *, [data-baseweb="popover"] li {{ color:#fff !important; }}
[data-baseweb="popover"] ul {{ background:#0e1a2b !important; }}
[data-testid="stAlert"] {{ background:rgba(10,20,34,.85) !important; }}
[data-testid="stAlert"] * {{ color:#fff !important; }}
[data-testid="stProgress"] p {{ color:#e6edf5 !important; }}
@media (max-width:700px) {{ .kpis {{ grid-template-columns:1fr 1fr; }} .nav .by {{ display:none; }} }}
</style>"""


def score_ring(score: int) -> str:
    color = "#22c55e" if score >= 85 else "#f97316" if score >= 60 else "#ef4444"
    c = 2 * 3.1416 * 52
    return f"""<svg width="150" height="150" viewBox="0 0 120 120">
<circle cx="60" cy="60" r="52" stroke="rgba(148,163,184,.18)" stroke-width="10" fill="none"/>
<circle cx="60" cy="60" r="52" stroke="{color}" stroke-width="10" fill="none" stroke-linecap="round"
 stroke-dasharray="{c * score / 100:.1f} {c:.1f}" transform="rotate(-90 60 60)"/>
<text x="60" y="62" text-anchor="middle" font-family="Space Grotesk, Inter, sans-serif" font-size="30" font-weight="700" fill="#fff">{score}</text>
<text x="60" y="80" text-anchor="middle" font-family="Inter" font-size="10" fill="#94a3b8">/ 100</text></svg>"""
