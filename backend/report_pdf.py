"""Generate an offline, bilingual report document from the authorized report only."""
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from unicodedata import category

from fastapi.responses import Response
from fontTools.ttLib import TTFont
from fpdf import FPDF


FONT = Path(__file__).with_name("report_fonts") / "NotoSansArabic.ttf"
INK = "#182824"
MUTED = "#465950"
ACCENT = "#376129"
LINE = "#C8D6CD"
PAPER = "#EDF5ED"
SEVERITIES = {"high": 0, "medium": 1, "low": 2}


@lru_cache(maxsize=1)
def characters():
    with TTFont(FONT, lazy=True) as font:
        return frozenset(font.getBestCmap())


def printable(value, limit=450):
    """Keep PDF typography stable with escaped control characters and bounded fields."""
    value = " ".join(str(value or "").split())
    cmap = characters()
    return "".join(char if ord(char) in cmap else "?" for char in value if category(char) != "Cf")[:limit]


class ReportDocument(FPDF):
    def __init__(self, language):
        super().__init__(format="A4")
        self.ar = language == "ar"
        self.set_margins(18, 18, 18)
        self.set_auto_page_break(True, 18)
        self.add_font("Noto", fname=FONT, variations={"": {"wght": 400}, "B": {"wght": 700}})
        self.set_text_shaping(True, direction="rtl" if self.ar else "ltr")
        self.set_title("Marsad Security Report")
        self.set_author("Marsad")
        self.set_lang(language)

    def translate(self, ar, en):
        return ar if self.ar else en

    def write_line(self, value, size=10, bold=False, color=INK, height=6, fill=False, direction=None):
        self.set_font("Noto", style="B" if bold else "", size=size)
        self.set_text_color(color)
        rtl = self.ar if direction is None else direction == "rtl"
        self.set_text_shaping(True, direction="rtl" if rtl else "ltr")
        self.multi_cell(w=0, h=height, text=value, align="R" if rtl else "L",
                        new_x="LMARGIN", new_y="NEXT", fill=fill, padding=(1.5, 3))
        self.set_text_shaping(True, direction="rtl" if self.ar else "ltr")

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(LINE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.write_line(f"MARSAD  /  {self.page_no()}", size=8, height=4, color=MUTED, direction="ltr")


def report_pdf(report, lang):
    pdf = ReportDocument(lang)
    t = pdf.translate
    pdf.add_page()
    pdf.set_fill_color(PAPER)
    pdf.write_line("MARSAD", size=12, bold=True, color=ACCENT, height=7, fill=True)
    pdf.write_line(t("تقرير المراجعة الأمنية", "Security review report"), size=24, bold=True, height=15, fill=True)
    pdf.ln(3)

    source = report.input_artifact or report.source
    if source and source.name:
        pdf.write_line(printable(source.name, 180), size=12, bold=True, direction="ltr")
    try:
        date = datetime.fromisoformat(report.created_at).date().isoformat()
    except ValueError:
        date = printable(report.created_at, 45)
    pdf.write_line(f"{t('تاريخ الفحص', 'Scan date')}  {date}", color=MUTED)
    pdf.write_line(t("النطاق: تحليل دفاعي للملفات المقدمة", "Scope: defensive review of the supplied files"), color=MUTED)
    if report.status == "partial":
        pdf.write_line(t("فحص جزئي: تعذر إكمال بعض خطوات التحليل.", "Partial scan: some checks could not finish."), bold=True)
    pdf.ln(4)

    groups = {}
    for finding in sorted(report.findings, key=lambda item: (SEVERITIES.get(item.severity, 9), item.rule, item.line)):
        groups.setdefault(finding.rule, []).append(finding)
    coverage = Counter(entry.status for entry in report.coverage or [])
    pdf.write_line(t("ملخص الفحص", "Scan summary"), size=15, bold=True, height=9)
    pdf.write_line(t(f"أنواع النتائج: {len(groups)}   |   مواضع الأدلة: {len(report.findings)}",
                     f"Finding types: {len(groups)}   |   Evidence locations: {len(report.findings)}"))
    if report.coverage is not None:
        applied = coverage["matched"] + coverage["clear"]
        pdf.write_line(t(f"قواعد تم تشغيلها: {applied}   |   قواعد غير منطبقة: {coverage['not_applicable']}",
                         f"Checks run: {applied}   |   Not applicable: {coverage['not_applicable']}"))
        if coverage["skipped"] or coverage["error"]:
            pdf.write_line(t(f"تم تخطيها: {coverage['skipped']}   |   تعذر تشغيلها: {coverage['error']}",
                             f"Skipped: {coverage['skipped']}   |   Could not run: {coverage['error']}"), color=MUTED)
    else:
        pdf.write_line(t("تفاصيل التغطية غير متاحة لهذا التقرير.", "Coverage details are unavailable for this report."), color=MUTED)
    pdf.ln(5)

    pdf.write_line(t("النتائج والإصلاحات", "Findings and recommended fixes"), size=16, bold=True, height=10)
    if not groups:
        pdf.write_line(t("لم يسجل التقرير أدلة مطابقة ضمن نطاق الفحص.", "No matching evidence was recorded within the scan scope."), color=MUTED)
    for rule, matches in groups.items():
        finding = matches[0]
        if pdf.will_page_break(43):
            pdf.add_page()
        label = {"high": t("عالية", "High"), "medium": t("متوسطة", "Medium"), "low": t("منخفضة", "Low")}.get(finding.severity, "")
        pdf.write_line(printable((finding.title_ar if pdf.ar else None) or finding.title, 160),
                       size=13, bold=True, height=8, fill=True)
        pdf.write_line(f"{label}   |   {t('عدد المواضع', 'Locations')}: {len(matches)}", size=9, color=MUTED)
        location = printable(finding.path or (source.name if source else ""), 120)
        location_str = f"{printable(rule, 60)}  /  {location + '  /  ' if location else ''}L{finding.line}"
        pdf.write_line(location_str, size=9, color=MUTED, direction="ltr")
        if finding.evidence:
            pdf.write_line(printable(finding.evidence, 225), size=9, color=MUTED, direction="ltr")
        advice = (finding.remediation_ar if pdf.ar else None) or finding.remediation
        pdf.write_line(t("الإصلاح: ", "Fix: ") + printable(advice))
        if len(matches) > 1:
            pdf.write_line(t("باقي المواضع موجودة في التقرير داخل مرصد.",
                             "The full report in Marsad includes the remaining locations."), size=9, color=MUTED)
        pdf.ln(3)
    return bytes(pdf.output())


def pdf_download(report, lang):
    return Response(report_pdf(report, lang), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="marsad-report-{lang}.pdf"',
        "Cache-Control": "no-store",
    })
