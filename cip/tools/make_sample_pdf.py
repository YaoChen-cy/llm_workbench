"""
Generate a FICTIONAL CIP "Monthly Change in Provision" memo for testing.
All names, numbers and events are invented.

    python tools/make_sample_pdf.py  ->  input/2026-10/Harborline_Home_Furnishings.pdf
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "input" / "2026-10" / "Harborline_Home_Furnishings.pdf"

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=12, spaceBefore=14, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=10, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=6)
TITLE = ParagraphStyle("Title", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=14, spaceAfter=10)


def bullets(items):
    return ListFlowable([ListItem(Paragraph(t, BODY), leftIndent=12) for t in items],
                        bulletType="bullet", start="•", leftIndent=12)


def grid(data, widths):
    t = Table(data, colWidths=widths)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DDE3EA")),
    ]))
    return t


def on_page(c, doc):
    c.saveState()
    c.setFont("Helvetica", 7.5)
    c.drawString(inch, letter[1] - 0.5 * inch, "CONFIDENTIAL - INTERNAL USE ONLY   |   Credit Information Package")
    c.drawRightString(letter[0] - inch, 0.5 * inch, f"Page {doc.page}")
    c.restoreState()


story = [
    Paragraph("Credit Information Package (CIP) - Monthly Change in Provision", TITLE),
    grid([
        ["Field", "Value", "Field", "Value"],
        ["Borrower", "Harborline Home Furnishings Inc.", "Memo Date", "October 12, 2026"],
        ["Industry", "Home Furnishings Retail", "Risk Rating", "Doubtful (9)"],
        ["Account Officer", "J. Doe", "Facility", "1st Lien Term Loan B"],
        ["Total Commitment", "$45.0mm", "Accrual Status", "Non-accrual"],
    ], [1.2 * inch, 2.0 * inch, 1.2 * inch, 1.6 * inch]),
    Spacer(1, 10),
    Paragraph("Exposure - Pre-Restructuring", H2),
    grid([
        ["Facility", "Commitment", "Outstanding", "Provision", "Net Exposure"],
        ["1st Lien TLB", "$45.0mm", "$45.0mm", "$29.3mm", "$15.7mm"],
        ["Total", "$45.0mm", "$45.0mm", "$29.3mm", "$15.7mm"],
    ], [1.4 * inch] * 5),
    Spacer(1, 6),
    Paragraph("Exposure - Post-Restructuring (Pro Forma)", H2),
    grid([
        ["Instrument", "Face", "Fair Value", "Provision / Write-down", "Net Carrying"],
        ["Exit Term Loan (pro-rata)", "$7.9mm", "$7.5mm", "-", "$7.5mm"],
        ["Reorganized Equity (4.5%)", "n/a", "$8.2mm", "-", "$8.2mm"],
        ["Total", "", "$15.7mm", "$29.3mm", "$15.7mm"],
    ], [1.6 * inch, 1.0 * inch, 1.0 * inch, 1.6 * inch, 1.0 * inch]),

    Paragraph("Company Overview", H1),
    Paragraph("Harborline Home Furnishings Inc. (\"Harborline\" or the \"Company\") is a vertically integrated "
              "designer, manufacturer and omni-channel retailer of mid-priced residential furniture, headquartered in "
              "Charlotte, North Carolina. The Company operates 118 showrooms across 22 states and generated FY2025 "
              "revenue of $1.42bn and Adj. EBITDA of $71mm. Harborline was acquired by Crestmark Capital Partners in "
              "a 2021 LBO at approximately 7.0x EBITDA.", BODY),
    Paragraph("Business Segments", H2),
    Paragraph("The Company operates through three brands: Harborline (upholstery and case goods, ~62% of revenue), "
              "Pell &amp; Row (premium outdoor furniture, ~24%) and Nestly (e-commerce-only value brand, ~14%). "
              "Approximately 70% of upholstery is produced in two domestic plants, with case goods and outdoor "
              "products sourced primarily from Vietnam and Malaysia.", BODY),
    Paragraph("Capital Structure", H2),
    Paragraph("As of the petition date, funded debt totaled approximately $1.35bn, comprising a $200mm ABL revolver "
              "($140mm drawn), an $850mm 1st Lien Term Loan B maturing 2028 (S+425) and $360mm of 9.25% 2nd Lien "
              "Senior Secured Notes due 2029. Total leverage stood at 19.3x LTM Adj. EBITDA of $70mm, compared with "
              "6.1x at closing of the LBO. The Bank holds $45.0mm of the 1st Lien TLB (5.3% of the tranche).", BODY),

    Paragraph("Reason for Rating \"Doubtful\"", H1),
    Paragraph("Operational Drivers", H2),
    Paragraph("Demand for big-ticket home furnishings has contracted sharply since 2023 as existing home sales fell to "
              "multi-decade lows, removing the primary purchase trigger for the Company's core customer. Harborline's "
              "same-store sales declined 9% in FY2024 and a further 14% in FY2025.", BODY),
    bullets([
        "Tariffs on Southeast Asian imports introduced in 2025 increased landed costs on case goods by "
        "approximately 18%, of which management was able to pass through less than half.",
        "Showroom labor and occupancy costs remained largely fixed, resulting in severe negative operating leverage.",
        "A failed ERP migration in Q3 2025 disrupted order fulfillment for roughly ten weeks, driving elevated "
        "cancellations and customer concessions.",
    ]),
    Paragraph("Financial Metrics", H2),
    Paragraph("Adj. EBITDA declined from $212mm in FY2022 to $71mm in FY2025, with margin compressing from 12.4% to "
              "5.0%. LTM Adj. EBITDA as of June 2026 was $70mm. Liquidity fell to $38mm at the end of Q1 2026, "
              "below the $50mm springing covenant threshold under the ABL.", BODY),
    Paragraph("Strategic Pivot", H2),
    Paragraph("Management initially pursued an operational turnaround in 2025, including the closure of 14 "
              "underperforming showrooms and a SKU rationalization program. As the turnaround failed to gain traction, "
              "the Company engaged Kirkland-Ellison LLP and Hollow Ridge Partners as restructuring advisors in "
              "February 2026, elected to skip the March 2026 coupon on the 2nd Lien Notes and entered into forbearance "
              "with the ABL lenders. The credit was downgraded to Doubtful in April 2026.", BODY),

    Paragraph("Transactional Updates", H1),
    Paragraph("On August 4, 2026, Harborline and its subsidiaries filed voluntary petitions under Chapter 11 of the "
              "U.S. Bankruptcy Code in the District of Delaware, supported by a Restructuring Support Agreement (RSA) "
              "signed by holders of approximately 78% of the 1st Lien TLB. The Bank is a signatory to the RSA.", BODY),
    Paragraph("The Court granted final approval of a $150mm DIP facility on September 2, 2026, consisting of $100mm "
              "of new money and a $50mm roll-up of prepetition 1st Lien claims, provided pro-rata by participating "
              "1st Lien lenders. The Bank elected not to participate in the DIP.", BODY),
    Paragraph("Under the Plan of Reorganization filed on September 18, 2026, the treatment of claims is as follows:", BODY),
    bullets([
        "1st Lien TLB holders will receive, on a pro-rata basis, (i) a $150mm Exit Term Loan and (ii) 85% of the "
        "reorganized equity, subject to dilution by a 10% Management Incentive Plan.",
        "2nd Lien Noteholders will receive 15% of the reorganized equity plus warrants struck at a 1st Lien "
        "recovery-implied equity value, contingent on accepting the Plan.",
        "General unsecured creditors will share in a $6mm cash pool; the Plan contemplates a cramdown of this "
        "class should it vote to reject.",
        "Existing equity held by Crestmark Capital Partners will be cancelled for no recovery.",
    ]),
    Paragraph("The Disclosure Statement hearing is scheduled for October 28, 2026, with a targeted confirmation hearing "
              "in early December 2026.", BODY),

    Paragraph("Provision Rationale & Accounting Impact", H1),
    Paragraph("The specific provision was increased from $18.0mm to $29.3mm (65% of exposure) during September 2026, "
              "an increase of $11.3mm. The provision had previously been raised from $9.0mm to $18.0mm in April 2026 "
              "upon downgrade to Doubtful.", BODY),
    Paragraph("The increase reflects the valuation in the filed Disclosure Statement, which implies a total enterprise "
              "value of $420mm at the midpoint (6.0x LTM Adj. EBITDA), materially below the $600mm assumed in the "
              "prior provision analysis. After repayment of the DIP and ABL, implied recovery to 1st Lien lenders is "
              "approximately 35% of claim.", BODY),
    Paragraph("The Bank's pro-rata share of recovery comprises approximately $7.9mm of Exit Term Loan (fair value "
              "$7.5mm) and approximately 4.5% of reorganized equity (fair value $8.2mm), for a total estimated "
              "recovery of $15.7mm against a carrying value of $45.0mm. Upon emergence, the residual loss will be "
              "charged off against the specific provision with no further P&amp;L impact expected.", BODY),

    Paragraph("Outlook and Action Plan", H1),
    Paragraph("The Bank will continue to support the RSA and vote in favor of the Plan. Key risks to recovery include "
              "a contested confirmation hearing should the 2nd Lien Noteholders object to the valuation, and further "
              "deterioration in trading during the case.", BODY),
    bullets([
        "Monitor DIP budget compliance and weekly liquidity reporting.",
        "Engage with the Bank's Equity Holdings Group regarding the governance and eventual disposition of the "
        "reorganized equity.",
        "Re-assess the provision upon plan confirmation; emergence is targeted for Q1 2027.",
    ]),

    Spacer(1, 18),
    Paragraph("Sign-off", H1),
    grid([
        ["Role", "Name", "Signature", "Date"],
        ["Account Officer", "J. Doe", "", "10/12/2026"],
        ["Senior Credit Officer", "A. Smith", "", ""],
        ["Business Head", "R. Lee", "", ""],
    ], [1.6 * inch, 1.4 * inch, 1.6 * inch, 1.2 * inch]),
]

OUT.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(OUT), pagesize=letter, topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                  title="CIP Memo - Harborline").build(story, onFirstPage=on_page, onLaterPages=on_page)
print("wrote", OUT)
