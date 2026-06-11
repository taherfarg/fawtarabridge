"""Human-readable invoice PDF (FR-7.1) — simple bilingual A4 template.

Arabic rendering: NotoNaskhArabic with reshaping + bidi; Latin text uses
NotoSans with the Arabic font as fallback, so mixed strings stay readable.
"""

from datetime import UTC, datetime
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.lifecycle.state_machine import InvoiceStatus
from app.pintae import CanonicalInvoice, get_engine
from app.pintae.v1.calc import line_net

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

PAGE_WIDTH = 210
MARGIN = 12
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN


def _ar(text: str) -> str:
    """Shape + reorder Arabic for PDF rendering."""
    return get_display(arabic_reshaper.reshape(text))


class _InvoicePdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="portrait", format="A4")
        self.set_margins(MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=15)
        self.add_font("noto", style="", fname=str(FONTS_DIR / "NotoSans-Regular.ttf"))
        self.add_font("notoarabic", style="", fname=str(FONTS_DIR / "NotoNaskhArabic-Regular.ttf"))
        self.set_fallback_fonts(["notoarabic"])
        self.set_font("noto", size=9)


def render_invoice_pdf(
    canonical: CanonicalInvoice,
    *,
    status: str,
    spec_version: str | None,
    xml_hash: str | None = None,
) -> bytes:
    totals = get_engine(spec_version).totals(canonical)
    pdf = _InvoicePdf()
    pdf.add_page()

    def row(label_en: str, label_ar: str, value: str, bold: bool = False) -> None:
        pdf.set_font("noto", size=10 if bold else 9)
        pdf.cell(60, 6, label_en)
        pdf.cell(70, 6, value, align="C")
        pdf.cell(0, 6, _ar(label_ar), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Header
    pdf.set_font("noto", size=16)
    pdf.cell(CONTENT_WIDTH / 2, 10, "TAX INVOICE")
    pdf.cell(0, 10, _ar("فاتورة ضريبية"), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # Supplier / buyer blocks
    pdf.set_font("noto", size=9)
    supplier = canonical.supplier
    buyer = canonical.buyer
    half = CONTENT_WIDTH / 2
    pdf.cell(half, 5, f"Supplier: {supplier.name}")
    pdf.cell(0, 5, f"Buyer: {buyer.name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if supplier.name_ar or buyer.name_ar:
        pdf.cell(half, 5, _ar(supplier.name_ar or ""))
        pdf.cell(0, 5, _ar(buyer.name_ar or ""), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(half, 5, f"TRN: {supplier.trn or '-'}")
    pdf.cell(0, 5, f"TRN: {buyer.trn or '-'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # Invoice meta
    row("Invoice number", "رقم الفاتورة", canonical.invoice_number)
    row("Issue date", "تاريخ الإصدار", canonical.issue_date.isoformat())
    if canonical.due_date:
        row("Due date", "تاريخ الاستحقاق", canonical.due_date.isoformat())
    row("Currency", "العملة", canonical.currency)
    pdf.ln(3)

    # Lines table
    headers = ["#", "Description", "Qty", "Unit price", "Disc.", "VAT", "Net (AED)"]
    widths = [8, 76, 16, 24, 18, 14, 30]
    pdf.set_font("noto", size=8)
    pdf.set_fill_color(235, 235, 235)
    for header, width in zip(headers, widths, strict=True):
        pdf.cell(width, 6, header, border=1, fill=True, align="C")
    pdf.ln()
    for line in canonical.lines:
        description = line.description
        if line.description_ar:
            description += f"  {_ar(line.description_ar)}"
        cells = [
            line.line_id,
            description,
            f"{line.quantity}",
            f"{line.unit_price}",
            f"{line.discount_amount}",
            f"{line.vat_rate}%",
            f"{line_net(line):.2f}",
        ]
        aligns = ["C", "L", "R", "R", "R", "C", "R"]
        for value, width, align in zip(cells, widths, aligns, strict=True):
            pdf.cell(width, 6, value, border=1, align=align)
        pdf.ln()
    pdf.ln(3)

    # Totals
    row("Total excluding VAT", "الإجمالي قبل الضريبة", f"AED {totals.tax_exclusive:.2f}")
    row("VAT total", "إجمالي الضريبة", f"AED {totals.tax_total:.2f}")
    row(
        "Total including VAT", "الإجمالي شامل الضريبة", f"AED {totals.tax_inclusive:.2f}", bold=True
    )
    row("Amount payable", "المبلغ المستحق", f"AED {totals.payable:.2f}", bold=True)
    pdf.ln(4)

    # Footer
    pdf.set_font("noto", size=7)
    pdf.set_text_color(110, 110, 110)
    if status != InvoiceStatus.ACCEPTED.value:
        pdf.cell(
            0,
            4,
            f"COPY - not cleared via the e-invoicing system (status: {status}) / "
            + _ar("نسخة - لم تُرسل عبر منظومة الفوترة الإلكترونية"),
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
    pdf.cell(
        0,
        4,
        f"Spec: {spec_version or '-'}   XML SHA-256: {xml_hash or '-'}",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0, 4, f"Generated by FawtaraBridge at {datetime.now(UTC).isoformat(timespec='seconds')}"
    )

    return bytes(pdf.output())
