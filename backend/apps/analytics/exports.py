"""
One place that turns report data into a downloadable CSV or PDF, so every
report offers both formats and the PDFs all look the same (Savanna green
header, company name, period, summary figures, striped table, page numbers).

Views pass ?export=csv or ?export=pdf through `export_format(request)` and
build an `export_response(...)` from the same rows they'd otherwise return
as JSON.
"""
import csv
import io
from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone

FORMATS = ('csv', 'xlsx', 'pdf')

# Savanna tokens (frontend/src/index.css) so PDFs match the app.
PRIMARY = '#0B4D33'
BORDER = '#E9E3D6'
STRIPE = '#FBF9F4'
MUTED = '#5E6B62'
TEXT = '#14231B'


def export_format(request):
    """'csv' / 'pdf' when the request asks for a download, else None."""
    fmt = (request.query_params.get('export') or '').lower()
    return fmt if fmt in FORMATS else None


class Section:
    """One table in a report. A report can have several (e.g. daily + by category)."""

    def __init__(self, columns, rows, heading=None, numeric=()):
        self.columns = list(columns)
        self.rows = [list(r) for r in rows]
        self.heading = heading
        # Column indexes to right-align in the PDF (amounts, counts, GB).
        self.numeric = set(numeric)


def export_response(fmt, *, filename, title, sections, subtitle='', summary=None):
    """
    fmt: 'csv' or 'pdf'. filename: without extension. sections: list of
    Section (or one Section). summary: optional [(label, value), ...] shown
    above the tables (and as leading rows in the CSV).
    """
    if isinstance(sections, Section):
        sections = [sections]
    if fmt == 'pdf':
        content = _pdf(title, subtitle, summary or [], sections)
        response = HttpResponse(content, content_type='application/pdf')
    elif fmt == 'xlsx':
        response = HttpResponse(
            _xlsx(title, subtitle, summary or [], sections),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    else:
        response = HttpResponse(_csv(title, subtitle, summary or [], sections), content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.{fmt}"'
    return response


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime('%Y-%m-%d %H:%M') if timezone.is_aware(value) else value.strftime('%Y-%m-%d %H:%M')
    if isinstance(value, float):
        return f'{value:,.2f}' if value % 1 else f'{value:,.0f}'
    return str(value)


def _csv(title, subtitle, summary, sections):
    out = io.StringIO()
    writer = csv.writer(out)
    # A single plain table keeps the classic "header row first" CSV shape
    # that spreadsheets and re-imports expect; anything richer gets titles.
    simple = len(sections) == 1 and not summary and not sections[0].heading
    if not simple:
        writer.writerow([title])
        if subtitle:
            writer.writerow([subtitle])
        for label, value in summary:
            writer.writerow([label, _csv_value(value)])
        writer.writerow([])
    for i, section in enumerate(sections):
        if section.heading and not simple:
            writer.writerow([section.heading])
        writer.writerow(section.columns)
        for row in section.rows:
            writer.writerow([_csv_value(v) for v in row])
        if i < len(sections) - 1:
            writer.writerow([])
    return out.getvalue()


def _csv_value(value):
    # Raw numbers in CSV (no thousands separators) so spreadsheets can sum them.
    if isinstance(value, datetime):
        return _cell(value)
    return '' if value is None else value


def _xlsx(title, subtitle, summary, sections):
    """
    Real Excel workbook: title block, summary, then each table with a bold
    header row, number formats on numeric columns, frozen header and
    sensible column widths -- numbers stay numbers so totals/filters work.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    company, _ = _branding()
    wb = Workbook()
    ws = wb.active
    ws.title = (title or 'Report')[:31]
    header_fill = PatternFill('solid', fgColor='E7F1EB')
    row = 1
    ws.cell(row=row, column=1, value=f'{company} · {title}' if company else title).font = Font(bold=True, size=14, color='0B4D33')
    row += 1
    if subtitle:
        ws.cell(row=row, column=1, value=subtitle).font = Font(color='5E6B62')
        row += 1
    ws.cell(row=row, column=1, value=f"Generated {timezone.localtime():%d %b %Y %H:%M} EAT").font = Font(color='8F978F', size=9)
    row += 2
    for label, value in summary:
        ws.cell(row=row, column=1, value=label).font = Font(color='5E6B62')
        ws.cell(row=row, column=2, value=value).font = Font(bold=True)
        row += 1
    if summary:
        row += 1

    widths = {}
    freeze_done = False
    for section in sections:
        if section.heading:
            ws.cell(row=row, column=1, value=section.heading).font = Font(bold=True, size=12)
            row += 1
        for col, name in enumerate(section.columns, start=1):
            cell = ws.cell(row=row, column=col, value=name)
            cell.font = Font(bold=True)
            cell.fill = header_fill
            widths[col] = max(widths.get(col, 0), len(str(name)))
        if not freeze_done and len(sections) == 1:
            ws.freeze_panes = ws.cell(row=row + 1, column=1)
            freeze_done = True
        row += 1
        for data_row in section.rows:
            for col, value in enumerate(data_row, start=1):
                if isinstance(value, datetime):
                    value = timezone.localtime(value).replace(tzinfo=None) if timezone.is_aware(value) else value
                cell = ws.cell(row=row, column=col, value=value)
                if (col - 1) in section.numeric and isinstance(value, (int, float)):
                    cell.number_format = '#,##0.00' if isinstance(value, float) else '#,##0'
                    cell.alignment = Alignment(horizontal='right')
                elif isinstance(value, datetime):
                    cell.number_format = 'yyyy-mm-dd hh:mm'
                widths[col] = max(widths.get(col, 0), min(len(_cell(value)), 50))
            row += 1
        row += 1
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = max(10, width + 2)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _branding():
    """(company name, logo ImageReader or None) from Settings -> Branding."""
    try:
        from apps.sitesettings.models import SiteSettings
        site = SiteSettings.load()
    except Exception:
        return '', None
    logo = None
    if site.logo:
        try:
            from reportlab.lib.utils import ImageReader
            with site.logo.open('rb') as fh:
                logo = ImageReader(io.BytesIO(fh.read()))
        except Exception:
            logo = None  # missing/unreadable file: brand with the name only
    return site.company_name or '', logo


def _pdf(title, subtitle, summary, sections):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    wide = max((len(s.columns) for s in sections), default=0) > 5
    pagesize = landscape(A4) if wide else A4
    buffer = io.BytesIO()
    company, logo = _branding()
    generated = timezone.localtime().strftime('%d %b %Y %H:%M EAT')

    def chrome(canvas, doc):
        width, height = pagesize
        canvas.saveState()
        band = 24 * mm
        canvas.setFillColor(colors.HexColor(PRIMARY))
        canvas.rect(0, height - band, width, band, stroke=0, fill=1)
        x = 15 * mm
        if logo:
            # Logo on a white badge so dark or transparent logos stay visible.
            badge = 15 * mm
            by = height - band + (band - badge) / 2
            canvas.setFillColor(colors.white)
            canvas.roundRect(x, by, badge, badge, 3 * mm, stroke=0, fill=1)
            pad = 1.5 * mm
            canvas.drawImage(logo, x + pad, by + pad, badge - 2 * pad, badge - 2 * pad,
                             preserveAspectRatio=True, anchor='c', mask='auto')
            x += badge + 5 * mm
        canvas.setFillColor(colors.white)
        if company:
            canvas.setFont('Helvetica-Bold', 9)
            canvas.drawString(x, height - 9.5 * mm, company.upper())
            canvas.setFont('Helvetica-Bold', 15)
            canvas.drawString(x, height - 17 * mm, title)
        else:
            canvas.setFont('Helvetica-Bold', 15)
            canvas.drawString(x, height - 14 * mm, title)
        canvas.setFont('Helvetica', 8.5)
        canvas.drawRightString(width - 15 * mm, height - 14 * mm, f'Generated {generated}')
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.setFont('Helvetica', 8)
        canvas.drawString(15 * mm, 10 * mm, f'{company} · {title}' if company else title)
        canvas.drawRightString(width - 15 * mm, 10 * mm, f'Page {doc.page}')
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer, pagesize=pagesize, title=title, author=company,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=32 * mm, bottomMargin=18 * mm,
    )
    sub_style = ParagraphStyle('sub', fontName='Helvetica', fontSize=10, textColor=colors.HexColor(MUTED), leading=13)
    head_style = ParagraphStyle('head', fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor(TEXT), leading=14, spaceBefore=6)
    cell_style = ParagraphStyle('cell', fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor(TEXT), leading=10.5)

    story = []
    if subtitle:
        story += [Paragraph(subtitle, sub_style), Spacer(1, 4 * mm)]

    if summary:
        cells = [[Paragraph(f'<font color="{MUTED}" size="8">{label}</font><br/><b>{_cell(value)}</b>', cell_style)
                  for label, value in summary]]
        box = Table(cells, colWidths=[(doc.width / len(summary))] * len(summary))
        box.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
            ('INNERGRID', (0, 0), (-1, -1), 0.6, colors.HexColor(BORDER)),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(STRIPE)),
            ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story += [box, Spacer(1, 6 * mm)]

    for section in sections:
        if section.heading:
            story += [Paragraph(section.heading, head_style), Spacer(1, 2 * mm)]
        if not section.rows:
            story += [Paragraph('No data for this period.', sub_style), Spacer(1, 5 * mm)]
            continue
        data = [[Paragraph(f'<b>{c}</b>', cell_style) for c in section.columns]]
        for row in section.rows:
            data.append([Paragraph(_cell(v).replace('&', '&amp;').replace('<', '&lt;'), cell_style) for v in row])
        table = Table(data, repeatRows=1, colWidths=[doc.width / len(section.columns)] * len(section.columns))
        style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E7F1EB')),
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.HexColor(PRIMARY)),
            ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor(BORDER)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        for r in range(2, len(data), 2):
            style.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor(STRIPE)))
        for col in section.numeric:
            for r in range(len(data)):
                data[r][col].style = ParagraphStyle(f'num{col}', parent=cell_style, alignment=2)
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 6 * mm)]

    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    return buffer.getvalue()
