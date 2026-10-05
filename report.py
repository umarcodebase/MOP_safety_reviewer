"""MOP Safety Reviewer - PDF report builder. Created by Umar Shahzad."""
from __future__ import annotations

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

APP_NAME = "MOP Safety Reviewer"
CREATOR = "Umar Shahzad"
NAVY, TEAL, GREY = (15, 32, 56), (0, 150, 136), (110, 117, 128)
SEV_COLOR = {"Critical": (192, 28, 40), "High": (230, 81, 0), "Medium": (219, 160, 0), "Low": (46, 125, 50)}
GO_COLOR = {"Go": (46, 125, 50), "Go with fixes": (230, 81, 0), "No-go": (192, 28, 40)}


def _t(s) -> str:
    """Core PDF fonts are Latin-1: replace common unicode and drop the rest."""
    s = str(s or "")
    for a, b in {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
                 "•": "-", "→": "->", "≤": "<=", "≥": ">=", " ": " ", "…": "..."}.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


class Report(FPDF):
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 18, "F")
        self.set_xy(12, 5)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 13)
        self.cell(100, 8, APP_NAME)
        self.set_font("Helvetica", "", 8)
        self.set_xy(110, 5)
        self.cell(88, 8, _t(f"Procedure Risk Review  |  Created by {CREATOR}"), align="R")
        self.set_text_color(0, 0, 0)
        self.set_y(24)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*GREY)
        self.cell(0, 5, _t(f"{APP_NAME} by {CREATOR}  |  Advisory only - a qualified engineer must approve every MOP"
                           f"  |  Page {self.page_no()}/{{nb}}"), align="C")

    def h2(self, text):
        if self.get_y() > 245:
            self.add_page()
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 7, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*TEAL)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y(), self.l_margin + 30, self.get_y())
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def para(self, text, size=9.5, style=""):
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, 5, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def pill(self, text, color, w=28):
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(w, 5.5, _t(text), fill=True, align="C")
        self.set_text_color(0, 0, 0)


def build_pdf(res: dict, profile: dict, exec_log: dict | None = None) -> bytes:
    pdf = Report()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(12, 24, 12)
    pdf.add_page()

    # ---- title block
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 8, _t(res["title"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY)
    meta = [("Prepared for", f"{profile.get('name') or '-'} ({profile.get('role', '-')})"),
            ("Site / facility", profile.get("site") or "-"),
            ("Generated", datetime.now().strftime("%d %b %Y, %H:%M")),
            ("Analysis mode", res["mode"]),
            ("Document", f"{res['pages']} pages, {len(res['steps'])} steps, ID {res['doc_hash']}")]
    for k, v in meta:
        pdf.cell(32, 5, _t(k))
        pdf.cell(0, 5, _t(v), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    # ---- score card
    pdf.ln(3)
    y = pdf.get_y()
    pdf.set_fill_color(240, 244, 248)
    pdf.rect(12, y, 186, 22, "F")
    sc = res["score"]
    col = SEV_COLOR["Low"] if sc >= 85 else SEV_COLOR["High"] if sc >= 60 else SEV_COLOR["Critical"]
    pdf.set_xy(16, y + 3)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*col)
    pdf.cell(30, 14, str(sc))
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.set_xy(40, y + 9)
    pdf.cell(20, 6, "/ 100")
    pdf.set_xy(62, y + 4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(70, 6, _t(res["grade"]))
    counts = {s: sum(1 for f in res["findings"] if f["severity"] == s) for s in SEV_COLOR}
    pdf.set_xy(62, y + 12)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(80, 5, _t("  ".join(f"{k}: {v}" for k, v in counts.items())))
    pdf.set_xy(160, y + 8)
    pdf.pill(res.get("go_decision", "-"), GO_COLOR.get(res.get("go_decision"), GREY), 34)
    pdf.set_y(y + 26)

    pdf.h2("Executive summary")
    pdf.para(res.get("summary", ""))

    pdf.h2("Pre-job briefing")
    for line in str(res.get("briefing", "")).split("\n"):
        if line.strip():
            pdf.para(f"-  {line.strip().lstrip('-* ')}")

    # ---- full attention steps
    hot = [s for s in res["steps"] if s["risk"] == "Full attention"]
    pdf.h2(f"Full-attention steps ({len(hot)})")
    if not hot:
        pdf.para("No high-risk steps detected.")
    for s in hot:
        a = res["attention"].get(s["num"], {})
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*SEV_COLOR["Critical"])
        pdf.cell(16, 5, _t(f"Step {s['num']}"))
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 5, _t(s["text"][:300]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        why = a.get("why") or "; ".join(s["reasons"])
        pdf.set_x(28)
        pdf.set_font("Helvetica", "I", 8.5)
        pdf.multi_cell(0, 4.5, _t(f"Risk: {why}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if a.get("watch_for"):
            pdf.set_x(28)
            pdf.multi_cell(0, 4.5, _t(f"Watch for: {a['watch_for']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1.5)

    # ---- findings
    pdf.h2(f"Findings ({len(res['findings'])})")
    for i, f in enumerate(res["findings"], 1):
        if pdf.get_y() > 255:
            pdf.add_page()
        pdf.pill(f["severity"], SEV_COLOR[f["severity"]], 20)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.cell(0, 5.5, _t(f"  {i}. {f['title']}   [{f['category']} - {f['source']}]"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.para(f["detail"], 9)
        pdf.set_text_color(*TEAL)
        pdf.para(f"Fix: {f['recommendation']}", 9, "B")
        pdf.set_text_color(0, 0, 0)
        if f["steps"]:
            pdf.para(f"Steps: {', '.join(f['steps'])}", 8, "I")
        pdf.ln(2)

    # ---- execution checklist
    pdf.add_page()
    pdf.h2("Execution checklist")
    pdf.para("Tick each step only after the expected result is confirmed. Full-attention steps are hold points.", 8.5, "I")
    pdf.ln(1)
    exec_log = exec_log or {}
    for s in res["steps"]:
        if pdf.get_y() > 268:
            pdf.add_page()
        log = exec_log.get(s["num"])
        hot = s["risk"] == "Full attention"
        pdf.set_font("Helvetica", "B" if hot else "", 8.5)
        pdf.set_text_color(*(SEV_COLOR["Critical"] if hot else (0, 0, 0)))
        box = "[X]" if log else "[  ]"
        pdf.cell(10, 5, box)
        pdf.cell(12, 5, _t(s["num"]))
        pdf.set_text_color(0, 0, 0)
        x = pdf.get_x()
        pdf.multi_cell(118, 5, _t(s["text"][:260] + ("  [HOLD POINT]" if hot else "")))
        yy = pdf.get_y()
        pdf.set_xy(x + 120, yy - 5)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*GREY)
        pdf.cell(44, 5, _t(f"{log['time']}  {log['by']}" if log else "Time: ______ Init: ____"))
        pdf.set_text_color(0, 0, 0)
        pdf.set_y(yy + 1)

    # ---- sign-off
    pdf.ln(4)
    pdf.h2("Sign-off")
    pdf.set_font("Helvetica", "", 9.5)
    for role in ("Prepared by", "Reviewed by", "Approved by"):
        pdf.cell(40, 9, role)
        pdf.cell(70, 9, "Name: ____________________")
        pdf.cell(0, 9, "Signature / date: ________________", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)
    pdf.para(f"Generated by {APP_NAME} - created by {CREATOR}. This report is decision support only; "
             "it does not replace the site's engineering review, change management or a qualified person's judgement.", 7.5, "I")
    return bytes(pdf.output())
