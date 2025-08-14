# export_audit_pack.py
from __future__ import annotations
from typing import List, Dict
from fpdf import FPDF

def build_audit_pack(council_name: str, cards: List[Dict]) -> bytes:
    pdf = FPDF(); pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page(); pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"{council_name} — PolicySimplify Audit Pack", ln=1)
    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Policies: {len(cards)}", ln=1); pdf.ln(4)

    for c in cards:
        pdf.set_font("Arial", "B", 14); pdf.cell(0, 8, f"Policy: {c.get('policy','')}", ln=1)
        pdf.set_font("Arial", "", 12);  pdf.cell(0, 8, f"Risk: {c.get('risk','')}", ln=1)
        pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Summary:", ln=1)
        pdf.set_font("Arial", "", 11);  pdf.multi_cell(0, 6, c.get("summary","")); pdf.ln(1)
        pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Checklist:", ln=1)
        pdf.set_font("Arial", "", 11);  pdf.multi_cell(0, 6, c.get("checklist","")); pdf.ln(1)
        pdf.set_font("Arial", "B", 12); pdf.cell(0, 8, "Risk details:", ln=1)
        pdf.set_font("Arial", "", 11);  pdf.multi_cell(0, 6, c.get("risk_explainer","")); pdf.ln(4)

    return bytes(pdf.output(dest="S").encode("latin1", "ignore"))
