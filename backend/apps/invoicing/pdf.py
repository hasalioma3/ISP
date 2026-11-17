"""
Invoice PDFs, drawn with ReportLab (already a dependency for report
exports, so nothing new to install on the Pi).

Five designs share one data model (`_data`) and a few drawing helpers:
  classic  - logo and company top-left, big INVOICE title right, shaded table
  modern   - full-width accent band header, tinted info cards
  minimal  - black on white, hairlines, generous whitespace
  bold     - accent sidebar holding company, bill-to and the amount due
  compact  - an 80 mm wide receipt for thermal printers / phone screens
Signed invoices carry the KRA eTIMS block (SCU details + QR code) that KRA
requires on every invoice reported through eTIMS.
"""
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

from apps.invoicing.models import InvoiceSettings

TEMPLATES = ['classic', 'modern', 'minimal', 'bold', 'compact']

INK = colors.HexColor('#1d2420')
MUTED = colors.HexColor('#6b746f')
LINE = colors.HexColor('#dfe3e0')
PAPER_TINT = colors.HexColor('#f5f7f6')


def money(v):
    return f'{Decimal(v):,.2f}'


def _accent(cfg):
    try:
        return colors.HexColor(cfg.accent_color or '#1f5f3f')
    except Exception:
        return colors.HexColor('#1f5f3f')


def _tint(color, amount=0.88):
    """A pale version of `color` (mixed toward white)."""
    return colors.Color(color.red + (1 - color.red) * amount, color.green + (1 - color.green) * amount,
                        color.blue + (1 - color.blue) * amount)


def _data(invoice, cfg):
    from apps.sitesettings.models import SiteSettings
    site = SiteSettings.load()
    logo = None
    if cfg.show_logo and site.logo:
        try:
            logo = ImageReader(site.logo.path)
        except Exception:
            logo = None
    company_lines = [l for l in (cfg.company_address or '').splitlines() if l.strip()]
    company_lines += [x for x in [cfg.company_phone or site.support_phone, cfg.company_email] if x]
    if cfg.company_pin:
        company_lines.append(f'KRA PIN: {cfg.company_pin}')
    bill_to = [l for l in [invoice.customer_name, invoice.customer_phone, invoice.customer_email] if l]
    bill_to += [l for l in (invoice.customer_address or '').splitlines() if l.strip()]
    if invoice.customer_pin:
        bill_to.append(f'KRA PIN: {invoice.customer_pin}')
    meta = [('Invoice no.', invoice.number), ('Date', f'{invoice.issue_date:%d %b %Y}')]
    if invoice.due_date and invoice.status != 'paid':
        meta.append(('Due', f'{invoice.due_date:%d %b %Y}'))
    if invoice.payment_ref:
        meta.append(('Payment ref', invoice.payment_ref))
    meta.append(('Account', getattr(invoice, 'sample_account', None) or invoice.customer.username))
    totals = [('Subtotal', money(invoice.subtotal))]
    if invoice.tax:
        totals.append((f'VAT {invoice.vat_rate.normalize():f}%', money(invoice.tax)))
    totals.append(('Total (KES)', money(invoice.total)))
    # Part-paid only: a fully paid invoice already says so with the PAID mark.
    if invoice.amount_paid and invoice.balance_due:
        totals.append(('Paid', money(invoice.amount_paid)))
        totals.append(('Balance due', money(invoice.balance_due)))
    return {
        'company': site.company_name, 'logo': logo, 'company_lines': company_lines, 'bill_to': bill_to,
        'meta': meta, 'totals': totals, 'lines': invoice.lines, 'notes': invoice.notes,
        'payment_details': cfg.payment_details, 'footer': cfg.footer_note, 'terms': cfg.terms,
        'status': invoice.status, 'title': 'TAX INVOICE' if invoice.tax else 'INVOICE',
    }


# --- shared pieces ------------------------------------------------------------

def _text_lines(c, x, y, lines, font='Helvetica', size=9, color=INK, leading=None, width=None):
    leading = leading or size + 3.5
    c.setFont(font, size)
    c.setFillColor(color)
    for line in lines:
        for part in (simpleSplit(line, font, size, width) if width else [line]):
            c.drawString(x, y, part)
            y -= leading
    return y


def _logo(c, d, x, y_top, max_w=42 * mm, max_h=18 * mm):
    """Draw the logo with its top-left at (x, y_top); returns its height (0 if none)."""
    if not d['logo']:
        return 0
    iw, ih = d['logo'].getSize()
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    c.drawImage(d['logo'], x, y_top - h, w, h, mask='auto')
    return h


def _table(c, d, x, y, width, accent, style='shaded'):
    """Line items. Returns the y below the table."""
    cols = [width * 0.56, width * 0.1, width * 0.16, width * 0.18]
    heads = ['Description', 'Qty', 'Unit price', 'Amount']
    row_h = 7.5 * mm
    if style == 'shaded':
        c.setFillColor(accent)
        c.rect(x, y - row_h, width, row_h, stroke=0, fill=1)
        head_color = colors.white
    elif style == 'tint':
        c.setFillColor(_tint(accent))
        c.roundRect(x, y - row_h, width, row_h, 2 * mm, stroke=0, fill=1)
        head_color = accent
    else:
        head_color = MUTED
    c.setFillColor(head_color)
    c.setFont('Helvetica-Bold', 8.5)
    cx = x + 3 * mm
    for i, (h, w) in enumerate(zip(heads, cols)):
        if i == 0:
            c.drawString(cx, y - row_h + 2.6 * mm, h.upper() if style == 'rule' else h)
        else:
            c.drawRightString(cx + w - 6 * mm, y - row_h + 2.6 * mm, h.upper() if style == 'rule' else h)
        cx += w
    y -= row_h
    if style == 'rule':
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.line(x, y, x + width, y)
    for n, line in enumerate(d['lines']):
        desc = simpleSplit(str(line['description']), 'Helvetica', 9.5, cols[0] - 6 * mm)
        h = max(row_h, (len(desc) * 4.4 + 3.4) * mm)
        if style == 'shaded' and n % 2:
            c.setFillColor(PAPER_TINT)
            c.rect(x, y - h, width, h, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont('Helvetica', 9.5)
        ty = y - 5 * mm
        for part in desc:
            c.drawString(x + 3 * mm, ty, part)
            ty -= 4.4 * mm
        cx = x + 3 * mm + cols[0]
        for value, w in zip([line['quantity'], money(line['unit_price']), money(line['amount'])], cols[1:]):
            c.drawRightString(cx + w - 6 * mm, y - 5 * mm, str(value))
            cx += w
        y -= h
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(x, y, x + width, y)
    return y


def _totals(c, d, x_right, y, width, accent, emphasis='bar'):
    for label, value in d['totals']:
        strong = label.startswith('Total') or label == 'Balance due'
        if strong and emphasis == 'bar':
            c.setFillColor(accent)
            c.rect(x_right - width, y - 8.5 * mm, width, 8.5 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont('Helvetica-Bold', 11)
            c.drawString(x_right - width + 3 * mm, y - 5.8 * mm, label)
            c.drawRightString(x_right - 3 * mm, y - 5.8 * mm, value)
            y -= 10 * mm
            continue
        c.setFillColor(INK if strong else MUTED)
        c.setFont('Helvetica-Bold' if strong else 'Helvetica', 11 if strong else 9.5)
        c.drawString(x_right - width + 3 * mm, y - 5 * mm, label)
        c.setFillColor(INK)
        c.drawRightString(x_right - 3 * mm, y - 5 * mm, value)
        if strong and emphasis == 'rule':
            c.setStrokeColor(INK)
            c.setLineWidth(0.8)
            c.line(x_right - width, y, x_right, y)
        y -= 7 * mm
    return y


def _qr(c, url, x, y, size):
    widget = QrCodeWidget(url)
    b = widget.getBounds()
    w, h = b[2] - b[0], b[3] - b[1]
    drawing = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _etims_block(c, invoice, x, y, width, compact=False):
    """KRA eTIMS details + QR. Returns y below it (or y unchanged if unsigned)."""
    if invoice.etims_status not in ('signed', 'credited') or not invoice.etims_signature:
        return y
    qr = 24 * mm if not compact else 30 * mm
    rows = [
        ('CU invoice no.', f'{invoice.etims_sdc_id}/{invoice.etims_receipt_no}' if invoice.etims_sdc_id else invoice.etims_receipt_no),
        ('Internal data', invoice.etims_internal_data),
        ('Receipt signature', invoice.etims_signature),
        ('Date', timezone.localtime(invoice.etims_signed_at).strftime('%d/%m/%Y %H:%M:%S') if invoice.etims_signed_at else ''),
    ]
    if invoice.etims_mrc_no:
        rows.append(('MRC no.', invoice.etims_mrc_no))
    if compact:
        c.setFont('Helvetica-Bold', 7.5)
        c.setFillColor(INK)
        c.drawCentredString(x + width / 2, y - 4 * mm, 'KRA eTIMS - SCU INFORMATION')
        y -= 7 * mm
        for label, value in rows:
            for part in simpleSplit(f'{label}: {value}', 'Helvetica', 7, width):
                c.setFont('Helvetica', 7)
                c.drawString(x, y, part)
                y -= 3.4 * mm
        _qr(c, invoice.etims_qr_url, x + (width - qr) / 2, y - qr - 1 * mm, qr)
        return y - qr - 4 * mm
    box_h = qr + 6 * mm
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.roundRect(x, y - box_h, width, box_h, 2 * mm, stroke=1, fill=0)
    _qr(c, invoice.etims_qr_url, x + 3 * mm, y - box_h + 3 * mm, qr)
    tx = x + qr + 8 * mm
    c.setFont('Helvetica-Bold', 8.5)
    c.setFillColor(INK)
    c.drawString(tx, y - 6 * mm, 'KRA eTIMS - SCU information')
    ty = y - 11 * mm
    for label, value in rows:
        c.setFont('Helvetica', 7.5)
        c.setFillColor(MUTED)
        c.drawString(tx, ty, label)
        c.setFillColor(INK)
        c.drawString(tx + 30 * mm, ty, str(value)[:80])
        ty -= 3.8 * mm
    return y - box_h - 4 * mm


def _stamp(c, d, x, y, accent):
    if d['status'] not in ('paid', 'void'):
        return
    text = 'PAID' if d['status'] == 'paid' else 'VOID'
    color = accent if text == 'PAID' else colors.HexColor('#b3261e')
    c.saveState()
    c.translate(x, y)
    c.rotate(14)
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(2)
    c.roundRect(-20 * mm, -6 * mm, 40 * mm, 12 * mm, 2 * mm, stroke=1, fill=0)
    c.setFont('Helvetica-Bold', 20)
    c.drawCentredString(0, -3 * mm, text)
    c.restoreState()


def _footer_notes(c, d, x, y, width):
    blocks = [('Notes', d['notes']), ('How to pay', d['payment_details'] if d['status'] != 'paid' else ''),
              ('Terms', d['terms'])]
    for title, body in blocks:
        if not body:
            continue
        c.setFont('Helvetica-Bold', 8.5)
        c.setFillColor(INK)
        c.drawString(x, y, title)
        y = _text_lines(c, x, y - 4.5 * mm, body.splitlines(), size=8.5, color=MUTED, width=width) - 2 * mm
    return y


def _page_footer(c, d, page_w, accent, y=12 * mm):
    if d['footer']:
        c.setFont('Helvetica-Oblique', 8.5)
        c.setFillColor(MUTED)
        c.drawCentredString(page_w / 2, y, d['footer'][:140])


# --- designs ----------------------------------------------------------------

def _classic(c, invoice, d, cfg, accent):
    W, H = A4
    m = 18 * mm
    y = H - m
    lh = _logo(c, d, m, y)
    ty = y - lh - (4 * mm if lh else 0)
    c.setFont('Helvetica-Bold', 13)
    c.setFillColor(INK)
    c.drawString(m, ty - 4 * mm, d['company'])
    ty = _text_lines(c, m, ty - 9 * mm, d['company_lines'], size=8.5, color=MUTED, width=85 * mm)
    c.setFont('Helvetica-Bold', 26)
    c.setFillColor(accent)
    c.drawRightString(W - m, y - 9 * mm, d['title'])
    my = y - 17 * mm
    for label, value in d['meta']:
        c.setFont('Helvetica', 8.5)
        c.setFillColor(MUTED)
        c.drawRightString(W - m - 42 * mm, my, label)
        c.setFillColor(INK)
        c.setFont('Helvetica-Bold', 8.5)
        c.drawRightString(W - m, my, str(value))
        my -= 4.6 * mm
    y = min(ty, my) - 8 * mm
    c.setFont('Helvetica-Bold', 8.5)
    c.setFillColor(accent)
    c.drawString(m, y, 'BILL TO')
    y = _text_lines(c, m, y - 5 * mm, d['bill_to'], size=9.5, width=90 * mm) - 6 * mm
    _stamp(c, d, W - m - 30 * mm, y + 14 * mm, accent)
    y = _table(c, d, m, y, W - 2 * m, accent, 'shaded') - 4 * mm
    y = _totals(c, d, W - m, y, 75 * mm, accent, 'bar') - 6 * mm
    y = _etims_block(c, invoice, m, y, W - 2 * m)
    _footer_notes(c, d, m, y - 2 * mm, W - 2 * m)
    _page_footer(c, d, W, accent)


def _modern(c, invoice, d, cfg, accent):
    W, H = A4
    m = 16 * mm
    band = 44 * mm
    c.setFillColor(accent)
    c.rect(0, H - band, W, band, stroke=0, fill=1)
    if d['logo']:
        c.setFillColor(colors.white)
        c.roundRect(m - 2 * mm, H - band + 8 * mm, 46 * mm, band - 16 * mm, 2 * mm, stroke=0, fill=1)
        _logo(c, d, m, H - 10 * mm, max_w=42 * mm, max_h=band - 20 * mm)
        name_x = m + 50 * mm
    else:
        name_x = m
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(name_x, H - 20 * mm, d['company'])
    _text_lines(c, name_x, H - 26 * mm, d['company_lines'][:3], size=8, color=_tint(accent, 0.75), width=80 * mm)
    c.setFont('Helvetica-Bold', 22)
    c.setFillColor(colors.white)
    c.drawRightString(W - m, H - 21 * mm, d['title'])
    c.setFont('Helvetica', 10)
    c.drawRightString(W - m, H - 28 * mm, invoice.number)
    y = H - band - 8 * mm
    card_w = (W - 2 * m - 6 * mm) / 2
    card_h = max(30 * mm, (len(d['bill_to']) * 4.4 + 12) * mm, (len(d['meta']) * 4.6 + 10) * mm)
    for i, (title, rows) in enumerate([('Billed to', d['bill_to']), ('Details', None)]):
        x = m + i * (card_w + 6 * mm)
        c.setFillColor(_tint(accent, 0.92))
        c.roundRect(x, y - card_h, card_w, card_h, 3 * mm, stroke=0, fill=1)
        c.setFont('Helvetica-Bold', 8)
        c.setFillColor(accent)
        c.drawString(x + 5 * mm, y - 7 * mm, title.upper())
        if rows is not None:
            _text_lines(c, x + 5 * mm, y - 13 * mm, rows, size=9.5, width=card_w - 10 * mm)
        else:
            ry = y - 13 * mm
            for label, value in d['meta']:
                c.setFont('Helvetica', 8.5)
                c.setFillColor(MUTED)
                c.drawString(x + 5 * mm, ry, label)
                c.setFont('Helvetica-Bold', 8.5)
                c.setFillColor(INK)
                c.drawRightString(x + card_w - 5 * mm, ry, str(value))
                ry -= 4.6 * mm
    y -= card_h + 8 * mm
    y = _table(c, d, m, y, W - 2 * m, accent, 'tint') - 4 * mm
    _stamp(c, d, m + 30 * mm, y - 12 * mm, accent)
    y = _totals(c, d, W - m, y, 78 * mm, accent, 'bar') - 6 * mm
    y = _etims_block(c, invoice, m, y, W - 2 * m)
    _footer_notes(c, d, m, y - 2 * mm, W - 2 * m)
    c.setFillColor(accent)
    c.rect(0, 0, W, 4 * mm, stroke=0, fill=1)
    _page_footer(c, d, W, accent, y=9 * mm)


def _minimal(c, invoice, d, cfg, accent):
    W, H = A4
    m = 22 * mm
    y = H - m
    c.setFont('Helvetica', 30)
    c.setFillColor(INK)
    c.drawString(m, y - 10 * mm, d['title'].title())
    lh = _logo(c, d, W - m - 36 * mm, y, max_w=36 * mm, max_h=14 * mm)
    y -= max(18 * mm, lh + 4 * mm)
    col = (W - 2 * m) / 3
    blocks = [('From', [d['company']] + d['company_lines']), ('To', d['bill_to']),
              ('Invoice', [f'{label}: {value}' for label, value in d['meta']])]
    lowest = y
    for i, (title, rows) in enumerate(blocks):
        x = m + i * col
        c.setFont('Helvetica', 7.5)
        c.setFillColor(MUTED)
        c.drawString(x, y, title.upper())
        lowest = min(lowest, _text_lines(c, x, y - 5 * mm, rows, size=8.5, width=col - 6 * mm))
    y = lowest - 10 * mm
    y = _table(c, d, m, y, W - 2 * m, accent, 'rule') - 4 * mm
    y = _totals(c, d, W - m, y, 70 * mm, accent, 'rule') - 8 * mm
    if d['status'] in ('paid', 'void'):
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(accent if d['status'] == 'paid' else colors.HexColor('#b3261e'))
        c.drawString(m, y + 14 * mm, d['status'].upper())
    y = _etims_block(c, invoice, m, y, W - 2 * m)
    _footer_notes(c, d, m, y - 2 * mm, W - 2 * m)
    _page_footer(c, d, W, accent)


def _bold(c, invoice, d, cfg, accent):
    W, H = A4
    side = 64 * mm
    c.setFillColor(accent)
    c.rect(0, 0, side, H, stroke=0, fill=1)
    x = 10 * mm
    y = H - 16 * mm
    if d['logo']:
        c.setFillColor(colors.white)
        c.roundRect(x - 2 * mm, y - 22 * mm, side - 16 * mm, 24 * mm, 2 * mm, stroke=0, fill=1)
        _logo(c, d, x, y, max_w=side - 20 * mm, max_h=20 * mm)
        y -= 30 * mm
    c.setFillColor(colors.white)
    c.setFont('Helvetica-Bold', 13)
    for part in simpleSplit(d['company'], 'Helvetica-Bold', 13, side - 18 * mm):
        c.drawString(x, y, part)
        y -= 6 * mm
    y = _text_lines(c, x, y - 1 * mm, d['company_lines'], size=8, color=_tint(accent, 0.7), width=side - 18 * mm)
    y -= 10 * mm
    c.setFont('Helvetica-Bold', 8)
    c.setFillColor(_tint(accent, 0.6))
    c.drawString(x, y, 'BILLED TO')
    y = _text_lines(c, x, y - 5 * mm, d['bill_to'], size=9, color=colors.white, width=side - 18 * mm)
    y -= 12 * mm
    c.setFont('Helvetica-Bold', 8)
    c.setFillColor(_tint(accent, 0.6))
    label = 'AMOUNT DUE' if invoice.balance_due else 'TOTAL PAID'
    c.drawString(x, y, label)
    c.setFont('Helvetica-Bold', 20)
    c.setFillColor(colors.white)
    c.drawString(x, y - 9 * mm, f'KES {money(invoice.balance_due or invoice.total)}')
    m = side + 12 * mm
    right = W - 14 * mm
    top = H - 18 * mm
    c.setFont('Helvetica-Bold', 34)
    c.setFillColor(INK)
    c.drawString(m, top - 10 * mm, d['title'])
    my = top - 20 * mm
    for lbl, value in d['meta']:
        c.setFont('Helvetica', 8.5)
        c.setFillColor(MUTED)
        c.drawString(m, my, lbl)
        c.setFont('Helvetica-Bold', 8.5)
        c.setFillColor(INK)
        c.drawString(m + 30 * mm, my, str(value))
        my -= 4.8 * mm
    _stamp(c, d, right - 25 * mm, top - 22 * mm, accent)
    y = my - 8 * mm
    y = _table(c, d, m, y, right - m, accent, 'shaded') - 4 * mm
    y = _totals(c, d, right, y, 70 * mm, accent, 'bar') - 6 * mm
    y = _etims_block(c, invoice, m, y, right - m)
    _footer_notes(c, d, m, y - 2 * mm, right - m)
    if d['footer']:
        c.setFont('Helvetica-Oblique', 8.5)
        c.setFillColor(MUTED)
        c.drawString(m, 12 * mm, d['footer'][:110])


def _compact_height(invoice, d):
    h = 92 * mm + len(d['lines']) * 9 * mm + len(d['bill_to']) * 4 * mm + len(d['company_lines']) * 4 * mm
    if invoice.etims_signature:
        h += 58 * mm
    if d['notes']:
        h += 15 * mm
    return h


def _compact(c, invoice, d, cfg, accent, size):
    W, H = size
    m = 5 * mm
    width = W - 2 * m
    y = H - 6 * mm
    lh = _logo(c, d, (W - 30 * mm) / 2, y, max_w=30 * mm, max_h=14 * mm)
    y -= lh + (3 * mm if lh else 0)
    c.setFont('Helvetica-Bold', 11)
    c.setFillColor(INK)
    c.drawCentredString(W / 2, y - 4 * mm, d['company'][:40])
    y -= 8 * mm
    c.setFont('Helvetica', 7.5)
    for line in d['company_lines']:
        c.drawCentredString(W / 2, y, line[:52])
        y -= 3.6 * mm

    def rule(yy):
        c.setDash(1, 2)
        c.setStrokeColor(MUTED)
        c.line(m, yy, W - m, yy)
        c.setDash()

    y -= 1 * mm
    rule(y)
    y -= 5 * mm
    c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(W / 2, y, d['title'])
    y -= 5 * mm
    for label, value in d['meta']:
        c.setFont('Helvetica', 7.5)
        c.drawString(m, y, label)
        c.drawRightString(W - m, y, str(value))
        y -= 3.8 * mm
    c.drawString(m, y, 'Customer')
    c.drawRightString(W - m, y, d['bill_to'][0][:30] if d['bill_to'] else '')
    y -= 3.8 * mm
    rule(y)
    y -= 5 * mm
    for line in d['lines']:
        for part in simpleSplit(str(line['description']), 'Helvetica', 7.5, width):
            c.setFont('Helvetica', 7.5)
            c.drawString(m, y, part)
            y -= 3.6 * mm
        c.drawString(m + 3 * mm, y, f"{line['quantity']} x {money(line['unit_price'])}")
        c.drawRightString(W - m, y, money(line['amount']))
        y -= 5 * mm
    rule(y + 1 * mm)
    y -= 3 * mm
    for label, value in d['totals']:
        strong = label.startswith('Total')
        c.setFont('Helvetica-Bold' if strong else 'Helvetica', 9 if strong else 7.5)
        c.drawString(m, y, label)
        c.drawRightString(W - m, y, value)
        y -= 4.5 * mm
    if d['status'] in ('paid', 'void'):
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(W / 2, y - 2 * mm, f"*** {d['status'].upper()} ***")
        y -= 8 * mm
    rule(y)
    y -= 2 * mm
    y = _etims_block(c, invoice, m, y, width, compact=True)
    if d['notes']:
        y = _text_lines(c, m, y - 2 * mm, d['notes'].splitlines(), size=7.5, color=MUTED, width=width)
    if d['footer']:
        c.setFont('Helvetica-Oblique', 7.5)
        c.setFillColor(MUTED)
        for part in simpleSplit(d['footer'], 'Helvetica-Oblique', 7.5, width):
            c.drawCentredString(W / 2, y - 3 * mm, part)
            y -= 3.6 * mm


def render_pdf(invoice, template=None):
    cfg = InvoiceSettings.load()
    template = template if template in TEMPLATES else (invoice.template if invoice.template in TEMPLATES else 'classic')
    d = _data(invoice, cfg)
    accent = _accent(cfg)
    buf = BytesIO()
    if template == 'compact':
        size = (80 * mm, _compact_height(invoice, d))
        c = canvas.Canvas(buf, pagesize=size)
        c.setTitle(f'Invoice {invoice.number}')
        _compact(c, invoice, d, cfg, accent, size)
    else:
        c = canvas.Canvas(buf, pagesize=A4)
        c.setTitle(f'Invoice {invoice.number}')
        c.setAuthor(d['company'])
        {'classic': _classic, 'modern': _modern, 'minimal': _minimal, 'bold': _bold}[template](c, invoice, d, cfg, accent)
    c.showPage()
    c.save()
    return buf.getvalue()


def sample_invoice():
    """An unsaved invoice for previewing designs in Settings (never stored)."""
    from datetime import timedelta
    from apps.invoicing.models import Invoice
    from apps.invoicing.services import compute_totals
    cfg = InvoiceSettings.load()
    lines, subtotal, rate, tax, total = compute_totals([
        {'description': 'Home Fibre 20 Mbps internet, 01 Dec 2026 - 31 Dec 2026', 'quantity': 1, 'unit_price': 2500},
        {'description': 'Router installation', 'quantity': 1, 'unit_price': 1000},
    ], cfg)
    today = timezone.localdate()
    inv = Invoice(number=f'{cfg.number_prefix}00042', template=cfg.default_template, status='paid', issue_date=today,
                  due_date=today + timedelta(days=cfg.due_days), customer_name='Jane Wanjiku',
                  customer_phone='0712345678', customer_email='jane@example.com', customer_address='Kilimani, Nairobi',
                  lines=lines, subtotal=subtotal, vat_rate=rate, tax=tax, total=total, amount_paid=total,
                  payment_ref='SKL7Q2XY9Z')
    inv.sample_account = 'jane.w'
    if cfg.etims_enabled:
        inv.etims_status, inv.etims_signature = 'signed', 'SAMPLE0SIGNATURE0ONLY'
        inv.etims_receipt_no, inv.etims_internal_data = '42', 'SAMPLE-INTERNAL-DATA'
        inv.etims_sdc_id, inv.etims_signed_at = 'KRACU0000000001', timezone.now()
    return inv
