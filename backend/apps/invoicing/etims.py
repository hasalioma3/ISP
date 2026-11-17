"""
KRA eTIMS -- Online Sales Control Unit (OSCU) API client.

Flow (per KRA's OSCU technical spec):
  1. Initialise the device once: POST /selectInitOsdcInfo {tin, bhfId,
     dvcSrlNo} -> data.info.cmcKey (plus sdcId/mrcNo). The serial comes from
     the eTIMS portal when the OSCU is registered for the PIN.
  2. Register the item sold (internet service) once: POST /saveItem.
  3. Each sale: POST /saveTrnsSalesOsdc with a strictly increasing invcNo
     per branch. KRA returns the receipt number, internal data and receipt
     signature that must be printed on the invoice with a QR code.
  4. A refund/cancellation is a credit note: the same call with
     rcptTyCd "R" and orgInvcNo = the original invcNo.
Every call after (1) sends headers tin, bhfId and cmcKey. A response is
successful only with resultCd "000".

Amounts are VAT-inclusive throughout, as eTIMS expects: taxAmt is the tax
part of taxblAmt (rate / (100 + rate)).
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

import requests
from django.db import transaction
from django.utils import timezone

from apps.invoicing.models import InvoiceSettings

logger = logging.getLogger('apps.invoicing')

BASE_URLS = {
    'sandbox': 'https://etims-api-sbx.kra.go.ke/etims-api',
    'production': 'https://etims-api.kra.go.ke/etims-api',
}
TAX_RATES = {'A': Decimal('0'), 'B': Decimal('16'), 'C': Decimal('0'), 'D': Decimal('0'), 'E': Decimal('8')}
PAYMENT_TYPES = {'cash': '01', 'mpesa': '06', 'bank': '04', 'balance': '07', 'other': '07'}
TIMEOUT = 30


class EtimsError(Exception):
    pass


def _q(v):
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def base_url(cfg):
    return (cfg.etims_base_url or BASE_URLS.get(cfg.etims_environment, BASE_URLS['sandbox'])).rstrip('/')


def _call(cfg, path, payload, with_key=True):
    headers = {'Content-Type': 'application/json', 'tin': cfg.company_pin, 'bhfId': cfg.etims_branch_id}
    if with_key:
        if not cfg.etims_cmc_key:
            raise EtimsError('eTIMS device is not initialised (no CMC key). Initialise it in Settings -> Invoices.')
        headers['cmcKey'] = cfg.etims_cmc_key
    try:
        resp = requests.post(f'{base_url(cfg)}{path}', json=payload, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise EtimsError(f'Could not reach KRA eTIMS: {e}')
    try:
        data = resp.json()
    except ValueError:
        raise EtimsError(f'KRA eTIMS answered HTTP {resp.status_code}: {resp.text[:300]}')
    if str(data.get('resultCd')) != '000':
        raise EtimsError(f"KRA eTIMS {data.get('resultCd')}: {data.get('resultMsg') or 'rejected'}")
    return data


def _check(cfg):
    if not cfg.company_pin:
        raise EtimsError('Set the company KRA PIN first.')
    if not cfg.etims_branch_id:
        raise EtimsError('Set the eTIMS branch ID (usually 00).')


def initialize(cfg=None):
    cfg = cfg or InvoiceSettings.load()
    _check(cfg)
    if not cfg.etims_device_serial:
        raise EtimsError('Enter the OSCU device serial number from the eTIMS portal.')
    data = _call(cfg, '/selectInitOsdcInfo', {
        'tin': cfg.company_pin, 'bhfId': cfg.etims_branch_id, 'dvcSrlNo': cfg.etims_device_serial,
    }, with_key=False)
    info = (data.get('data') or {}).get('info') or {}
    if not info.get('cmcKey'):
        raise EtimsError('KRA did not return a CMC key.')
    cfg.etims_cmc_key = info['cmcKey']
    cfg.etims_sdc_id = info.get('sdcId', '') or ''
    cfg.etims_mrc_no = info.get('mrcNo', '') or ''
    cfg.etims_initialized_at = timezone.now()
    cfg.save()
    return info


def item_code(cfg):
    # Country, item type 3 (service), packaging NT (net), quantity unit U, sequence.
    return cfg.etims_item_code or 'KE3NTU0000001'


def register_item(cfg=None, name='Internet service', price=0):
    cfg = cfg or InvoiceSettings.load()
    _check(cfg)
    code = item_code(cfg)
    _call(cfg, '/saveItem', {
        'itemCd': code, 'itemClsCd': cfg.etims_item_class_code, 'itemTyCd': '3', 'itemNm': name,
        'itemStdNm': None, 'orgnNatCd': 'KE', 'pkgUnitCd': 'NT', 'qtyUnitCd': 'U', 'taxTyCd': cfg.etims_tax_type,
        'btchNo': None, 'bcd': None, 'dftPrc': float(price), 'grpPrcL1': None, 'grpPrcL2': None, 'grpPrcL3': None,
        'grpPrcL4': None, 'grpPrcL5': None, 'addInfo': None, 'sftyQty': None, 'isrcAplcbYn': 'N', 'useYn': 'Y',
        'regrNm': 'ISP Billing', 'regrId': 'system', 'modrNm': 'ISP Billing', 'modrId': 'system',
    })
    if not cfg.etims_item_code:
        cfg.etims_item_code = code
        cfg.save(update_fields=['etims_item_code'])
    return code


def _next_invoice_no():
    with transaction.atomic():
        cfg = InvoiceSettings.objects.select_for_update().get(pk=1)
        cfg.etims_last_invoice_no += 1
        cfg.save(update_fields=['etims_last_invoice_no'])
        return cfg.etims_last_invoice_no


def build_sale(invoice, cfg, invc_no, receipt_type='S', original_no=0):
    tax_type = cfg.etims_tax_type
    rate = TAX_RATES.get(tax_type, Decimal('0'))
    items, taxable, tax_total = [], Decimal('0'), Decimal('0')
    for i, line in enumerate(invoice.lines, start=1):
        qty = Decimal(str(line.get('quantity') or 1))
        gross = _q(Decimal(str(line['amount'])) * (1 + invoice.vat_rate / 100)) if not _inclusive(invoice, cfg) \
            else _q(Decimal(str(line['amount'])))
        unit = _q(gross / qty) if qty else gross
        tax = _q(gross * rate / (100 + rate)) if rate else Decimal('0')
        taxable += gross
        tax_total += tax
        items.append({
            'itemSeq': i, 'itemCd': item_code(cfg), 'itemClsCd': cfg.etims_item_class_code,
            'itemNm': str(line.get('description') or 'Internet service')[:200], 'bcd': None,
            'pkgUnitCd': 'NT', 'pkg': float(qty), 'qtyUnitCd': 'U', 'qty': float(qty), 'prc': float(unit),
            'splyAmt': float(gross), 'dcRt': 0, 'dcAmt': 0, 'isrccCd': None, 'isrccNm': None, 'isrcRt': None,
            'isrcAmt': None, 'taxTyCd': tax_type, 'taxblAmt': float(gross), 'taxAmt': float(tax), 'totAmt': float(gross),
        })
    when = timezone.localtime()
    amounts = {}
    for code in 'ABCDE':
        amounts[f'taxblAmt{code}'] = float(taxable) if code == tax_type else 0
        amounts[f'taxRt{code}'] = float(TAX_RATES[code])
        amounts[f'taxAmt{code}'] = float(tax_total) if code == tax_type else 0
    method = invoice.transaction.payment_method if invoice.transaction_id else 'other'
    return {
        'tin': cfg.company_pin, 'bhfId': cfg.etims_branch_id, 'trdInvcNo': invoice.number, 'invcNo': invc_no,
        'orgInvcNo': original_no, 'custTin': invoice.customer_pin or None, 'custNm': invoice.customer_name[:60],
        'salesTyCd': 'N', 'rcptTyCd': receipt_type, 'pmtTyCd': PAYMENT_TYPES.get(method, '07'), 'salesSttsCd': '02',
        'cfmDt': when.strftime('%Y%m%d%H%M%S'), 'salesDt': invoice.issue_date.strftime('%Y%m%d'),
        'stockRlsDt': None, 'cnclReqDt': None, 'cnclDt': None,
        'rfdDt': when.strftime('%Y%m%d%H%M%S') if receipt_type == 'R' else None,
        'rfdRsnCd': '06' if receipt_type == 'R' else None,
        'totItemCnt': len(items), **amounts,
        'totTaxblAmt': float(taxable), 'totTaxAmt': float(tax_total), 'totAmt': float(taxable),
        'prchrAcptcYn': 'N', 'remark': None,
        'regrId': 'system', 'regrNm': 'ISP Billing', 'modrId': 'system', 'modrNm': 'ISP Billing',
        'receipt': {
            'custTin': invoice.customer_pin or None, 'custMblNo': invoice.customer_phone or None, 'rptNo': None,
            'trdeNm': None, 'adrs': None, 'topMsg': None, 'btmMsg': None, 'prchrAcptcYn': 'N',
        },
        'itemList': items,
    }


def _inclusive(invoice, cfg):
    return cfg.prices_include_vat or not cfg.vat_registered


def sign(invoice):
    """Report the sale to KRA and store the signature on the invoice."""
    cfg = InvoiceSettings.load()
    if not cfg.etims_enabled:
        raise EtimsError('eTIMS is turned off in Settings -> Invoices.')
    _check(cfg)
    if invoice.etims_status == 'signed':
        return invoice
    if invoice.status == 'void':
        raise EtimsError('A void invoice cannot be signed.')
    invoice.etims_status = 'pending'
    invoice.save(update_fields=['etims_status'])
    # Reuse the number of a previous failed attempt so a timeout that KRA did
    # in fact record doesn't leave a gap in the sequence.
    invc_no = invoice.etims_invoice_no or _next_invoice_no()
    invoice.etims_invoice_no = invc_no
    try:
        data = _call(cfg, '/saveTrnsSalesOsdc', build_sale(invoice, cfg, invc_no))
    except EtimsError as e:
        invoice.etims_status, invoice.etims_error = 'failed', str(e)[:2000]
        invoice.save(update_fields=['etims_status', 'etims_error', 'etims_invoice_no'])
        raise
    d = data.get('data') or {}
    invoice.etims_status = 'signed'
    invoice.etims_error = ''
    invoice.etims_receipt_no = str(d.get('curRcptNo') or d.get('rcptNo') or '')
    invoice.etims_total_receipt_no = str(d.get('totRcptNo') or '')
    invoice.etims_internal_data = d.get('intrlData') or ''
    invoice.etims_signature = d.get('rcptSign') or ''
    invoice.etims_sdc_id = d.get('sdcId') or cfg.etims_sdc_id
    invoice.etims_mrc_no = d.get('mrcNo') or cfg.etims_mrc_no
    invoice.etims_signed_at = timezone.now()
    invoice.etims_response = data
    invoice.save()
    return invoice


def credit_note(invoice):
    """Cancel a signed invoice with KRA by issuing a credit note."""
    cfg = InvoiceSettings.load()
    _check(cfg)
    if invoice.etims_status != 'signed' or not invoice.etims_invoice_no:
        return invoice
    no = _next_invoice_no()
    data = _call(cfg, '/saveTrnsSalesOsdc', build_sale(invoice, cfg, no, receipt_type='R',
                                                        original_no=invoice.etims_invoice_no))
    invoice.credit_note_no = no
    invoice.etims_status = 'credited'
    invoice.etims_response = {'sale': invoice.etims_response, 'credit_note': data}
    invoice.save(update_fields=['credit_note_no', 'etims_status', 'etims_response'])
    return invoice
