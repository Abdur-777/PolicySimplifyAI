# export_audit_pack.py — build a 1-click PDF Audit Pack
from fpdf import FPDF
import time

def _wrap(text: str, width: int = 100) -> str:
    # FPDF doesn't auto-wrap multi-line strings well; keep it simple
    lines, out = text.splitlines() if text else [], []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            out.append("")
            continue
        while len(ln) > width:
            out.append(ln[:width])
            ln = ln[width:]
        out.append(ln)
    return "\n".join(out)

def build_audit_pack(council_name: str, cards: list[dict]) -> bytes:
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)

    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    # Cover
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "PolicySimplify AI — Audit Pack", ln=1)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"Council: {council_name}", ln=1)
    pdf.cell(0, 8, f"Generated: {ts}", ln=1)
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, "This pack summarises policies processed by PolicySimplify AI with plain-English summaries, actionable checklists, and risk rationale. Use as evidence during audits.")
    pdf.ln(4)

    # Each policy
    for c in cards:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, c.get("policy","(Unknown policy)"), ln=1)

        created_at = c.get("created_at")
        if created_at:
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 6, "Processed: " + time.strftime("%Y-%m-%d %H:%M", time.localtime(created_at)), ln=1)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Risk:", ln=1)
        pdf.set_font("Helvetica", "", 11)
        risk_line = f"{c.get('risk','Medium')}"
        pdf.multi_cell(0, 6, risk_line)
        if c.get("risk_explainer"):
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 5, _wrap(c["risk_explainer"], 110))
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Summary:", ln=1)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, _wrap(c.get("summary",""), 110))
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, "Checklist:", ln=1)
        pdf.set_font("Helvetica", "", 11)
        checklist = c.get("checklist","")
        pdf.multi_cell(0, 6, _wrap(checklist, 110))

    return pdf.output(dest="S").encode("latin-1", errors="ignore")
