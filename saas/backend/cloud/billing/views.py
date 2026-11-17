import csv
import logging
from datetime import date

from django.db.models import Q, Sum
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cloud.accounts.permissions import IsPlatform, IsPlatformAdmin, IsTenantOwner
from cloud.billing.models import Collection, Invoice, LedgerEntry, PlatformPayment, Settlement
from cloud.core.models import PlatformSettings
from cloud.tenants.models import Tenant

logger = logging.getLogger('cloud.billing')


# --- serializers -------------------------------------------------------------

class CollectionSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', default=None)
    source_label = serializers.CharField(source='get_source_display')

    class Meta:
        model = Collection
        fields = ['id', 'receipt', 'tenant', 'tenant_name', 'source', 'source_label', 'amount', 'phone', 'account',
                  'payer_name', 'paid_at', 'routed_by', 'verified', 'verify_error', 'forwarded', 'forward_error', 'created_at']


class InvoiceSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name')
    status_label = serializers.CharField(source='get_status_display')

    class Meta:
        model = Invoice
        fields = ['id', 'number', 'tenant', 'tenant_name', 'period_start', 'period_end', 'plan_name', 'subscriber_count',
                  'count_detail', 'lines', 'subtotal', 'discount', 'amount', 'status', 'status_label', 'issued_at',
                  'due_at', 'paid_at', 'paid_via', 'payment_ref']


class SettlementSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name')
    status_label = serializers.CharField(source='get_status_display')
    requested_by = serializers.CharField(source='requested_by.email', default=None)
    approved_by = serializers.CharField(source='approved_by.email', default=None)

    class Meta:
        model = Settlement
        fields = ['id', 'tenant', 'tenant_name', 'amount', 'fee', 'method', 'destination', 'account_ref', 'status',
                  'status_label', 'requested_by', 'approved_by', 'mpesa_receipt', 'result_code', 'result_desc',
                  'created_at', 'submitted_at', 'completed_at']


class LedgerSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source='get_kind_display')
    created_by = serializers.CharField(source='created_by.email', default=None)

    class Meta:
        model = LedgerEntry
        fields = ['id', 'created_at', 'kind', 'kind_label', 'amount', 'reference', 'description', 'created_by']


def paginate(request, qs, serializer):
    pager = PageNumberPagination()
    page = pager.paginate_queryset(qs, request)
    return pager.get_paginated_response(serializer(page, many=True).data)


def _dates(qs, request, field):
    p = request.query_params
    if p.get('start'):
        qs = qs.filter(**{f'{field}__date__gte': p['start']})
    if p.get('end'):
        qs = qs.filter(**{f'{field}__date__lte': p['end']})
    return qs


def csv_response(name, header, rows):
    resp = HttpResponse(content_type='text/csv')
    resp['Content-Disposition'] = f'attachment; filename="{name}.csv"'
    w = csv.writer(resp)
    w.writerow(header)
    w.writerows(rows)
    return resp


# --- M-Pesa webhooks (Safaricom -> us) --------------------------------------
# Always answer 200/ResultCode 0 quickly: the money has already moved, and a
# non-zero answer only makes Safaricom retry.

ACK = {'ResultCode': 0, 'ResultDesc': 'Accepted'}


class MpesaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []


class StkCallbackView(MpesaView):
    def post(self, request, token):
        from cloud.billing.collections import handle_stk_callback
        tenant = Tenant.objects.filter(callback_token=token).first()
        if not tenant:
            raise Http404
        try:
            handle_stk_callback(tenant, request.data)
        except Exception:
            logger.exception('STK callback for %s failed', tenant.slug)
        return Response(ACK)


def _check_c2b(token):
    if token != PlatformSettings.load().c2b_secret:
        raise Http404


class C2BValidationView(MpesaView):
    def post(self, request, token):
        _check_c2b(token)
        return Response(ACK)


class C2BConfirmationView(MpesaView):
    def post(self, request, token):
        from cloud.billing.collections import handle_c2b_confirmation
        _check_c2b(token)
        try:
            handle_c2b_confirmation(request.data)
        except Exception:
            logger.exception('C2B confirmation failed: %s', request.data)
        return Response(ACK)


class PlatformStkCallbackView(MpesaView):
    """An ISP paying its platform invoice by STK."""

    def post(self, request, token):
        from cloud.billing import daraja
        from cloud.billing.invoicing import mark_paid
        if token != PlatformSettings.load().c2b_secret:
            raise Http404
        info = daraja.parse_stk_callback(request.data)
        pay = PlatformPayment.objects.filter(checkout_request_id=info['checkout_request_id']).select_related('invoice').first()
        if pay and pay.status == 'pending':
            if info['result_code'] == '0':
                pay.status, pay.receipt = 'paid', info['receipt']
                pay.save(update_fields=['status', 'receipt'])
                if pay.invoice.status == 'open':
                    mark_paid(pay.invoice, 'mpesa', info['receipt'])
                    from cloud.tenants.services import log
                    log(pay.invoice.tenant, 'billing', f'Invoice {pay.invoice.number} paid by M-Pesa ({info["receipt"]})')
            else:
                pay.status, pay.result_desc = 'failed', info['result_desc'][:255]
                pay.save(update_fields=['status', 'result_desc'])
        return Response(ACK)


class PayoutResultView(MpesaView):
    def post(self, request):
        from cloud.billing.settlement import handle_result
        try:
            handle_result(request.data)
        except Exception:
            logger.exception('Payout result failed: %s', request.data)
        return Response(ACK)


class PayoutTimeoutView(MpesaView):
    def post(self, request):
        from cloud.billing.settlement import handle_timeout
        handle_timeout(request.data)
        return Response(ACK)


# --- platform admin -------------------------------------------------------------

class CollectionListView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request):
        p = request.query_params
        qs = _dates(Collection.objects.select_related('tenant'), request, 'paid_at')
        if p.get('tenant'):
            qs = qs.filter(tenant_id=p['tenant'])
        if p.get('unallocated') in ('1', 'true'):
            qs = qs.filter(tenant__isnull=True)
        if p.get('problem') in ('1', 'true'):
            qs = qs.filter(Q(verified=False) | Q(forwarded=False, tenant__isnull=False))
        if p.get('search'):
            q = p['search']
            qs = qs.filter(Q(receipt__icontains=q) | Q(phone__icontains=q) | Q(account__icontains=q) | Q(payer_name__icontains=q))
        if p.get('export') == 'csv':
            return csv_response('payments', ['Receipt', 'ISP', 'Source', 'Amount', 'Phone', 'Account', 'Paid at', 'Verified', 'Forwarded'],
                                [[c.receipt, c.tenant.name if c.tenant else '', c.source, c.amount, c.phone, c.account,
                                  timezone.localtime(c.paid_at).strftime('%Y-%m-%d %H:%M') if c.paid_at else '', c.verified,
                                  c.forwarded] for c in qs[:20000]])
        totals = qs.filter(verified=True).aggregate(total=Sum('amount'))
        resp = paginate(request, qs, CollectionSerializer)
        resp.data['total_amount'] = totals['total'] or 0
        return resp


class CollectionActionView(APIView):
    """POST {action: allocate (tenant, account) | verify | forward}"""
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        from cloud.billing import collections
        from cloud.billing.tasks import forward_c2b, forward_stk, verify_collection
        c = Collection.objects.filter(pk=pk).select_related('tenant').first()
        if not c:
            return Response(status=404)
        action = request.data.get('action')
        if action == 'allocate':
            tenant = Tenant.objects.filter(pk=request.data.get('tenant')).first()
            if not tenant:
                return Response({'error': 'Choose the ISP'}, status=400)
            try:
                collections.allocate(c, tenant, request.data.get('account') or None, actor=request.user)
            except ValueError as e:
                return Response({'error': str(e)}, status=400)
        elif action == 'verify':
            verify_collection.delay(c.pk)
        elif action == 'forward' and c.tenant:
            if not c.verified:
                return Response({'error': 'Not confirmed by Safaricom yet -- re-check it first'}, status=400)
            if c.source == 'stk':
                forward_stk.delay(c.tenant_id, c.raw, c.pk)
            else:
                forward_c2b.delay(c.pk, request.data.get('account') or collections.route(c.account)[1] or c.account)
        else:
            return Response({'error': 'Unknown action'}, status=400)
        c.refresh_from_db()
        return Response(CollectionSerializer(c).data)


class InvoiceListView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request):
        p = request.query_params
        qs = _dates(Invoice.objects.select_related('tenant'), request, 'issued_at')
        if p.get('tenant'):
            qs = qs.filter(tenant_id=p['tenant'])
        if p.get('status'):
            qs = qs.filter(status=p['status'])
        if p.get('export') == 'csv':
            return csv_response('invoices', ['Number', 'ISP', 'Period', 'Subscribers', 'Amount', 'Status', 'Paid via'],
                                [[i.number, i.tenant.name, f'{i.period_start} - {i.period_end}', i.subscriber_count, i.amount,
                                  i.status, i.paid_via] for i in qs[:20000]])
        return paginate(request, qs, InvoiceSerializer)


class InvoiceCreateView(APIView):
    """POST {tenant, start?, end?, preview?} -- preview or issue an invoice now."""
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        from cloud.billing import invoicing
        tenant = Tenant.objects.filter(pk=request.data.get('tenant')).first()
        if not tenant:
            return Response({'error': 'Choose the ISP'}, status=400)
        try:
            start = date.fromisoformat(request.data['start']) if request.data.get('start') else invoicing.previous_month()[0]
            end = date.fromisoformat(request.data['end']) if request.data.get('end') else invoicing.previous_month()[1]
        except ValueError:
            return Response({'error': 'Dates must be YYYY-MM-DD'}, status=400)
        if end < start:
            return Response({'error': 'The period ends before it starts'}, status=400)
        try:
            if request.data.get('preview'):
                d = invoicing.build(tenant, start, end)
                return Response({'plan': d['plan'].name, 'period_start': d['period_start'], 'period_end': d['period_end'],
                                 'subscriber_count': d['count'], 'count_detail': d['detail'], 'lines': d['lines'],
                                 'subtotal': d['subtotal'], 'discount': d['discount'], 'amount': d['amount']})
            inv, created = invoicing.issue(tenant, start, end)
        except ValueError as e:
            return Response({'error': str(e)}, status=400)
        if not created:
            return Response({'error': f'{inv.number} already covers that period'}, status=409)
        return Response(InvoiceSerializer(inv).data, status=201)


class InvoiceActionView(APIView):
    """POST {action: void | mark_paid (ref) | deduct}"""
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        from cloud.billing.invoicing import mark_paid, pay_from_balance
        from cloud.tenants.services import log
        inv = Invoice.objects.filter(pk=pk).select_related('tenant').first()
        if not inv:
            return Response(status=404)
        action = request.data.get('action')
        if inv.status != 'open':
            return Response({'error': 'Only unpaid invoices can be changed'}, status=400)
        if action == 'void':
            inv.status = 'void'
            inv.save(update_fields=['status'])
            log(inv.tenant, 'billing', f'Invoice {inv.number} voided', actor=request.user)
        elif action == 'mark_paid':
            mark_paid(inv, 'manual', (request.data.get('ref') or '')[:100])
            log(inv.tenant, 'billing', f'Invoice {inv.number} marked paid by hand', actor=request.user)
        elif action == 'deduct':
            if not pay_from_balance(inv):
                return Response({'error': 'The balance held for this ISP does not cover it'}, status=400)
        else:
            return Response({'error': 'Unknown action'}, status=400)
        inv.refresh_from_db()
        return Response(InvoiceSerializer(inv).data)


class SettlementListView(APIView):
    permission_classes = [IsPlatform]

    def get(self, request):
        p = request.query_params
        qs = _dates(Settlement.objects.select_related('tenant', 'requested_by', 'approved_by'), request, 'created_at')
        if p.get('tenant'):
            qs = qs.filter(tenant_id=p['tenant'])
        if p.get('status'):
            qs = qs.filter(status__in=p['status'].split(','))
        return paginate(request, qs, SettlementSerializer)

    def post(self, request):
        """Create a payout for one ISP {tenant, amount?}, or run the schedule now {all: true}."""
        from cloud.billing.settlement import SettlementError, create, run_scheduled
        if not request.user.is_platform_admin:
            return Response({'error': 'Platform admins only.'}, status=403)
        if request.data.get('all'):
            return Response({'created': run_scheduled(force=True)})
        tenant = Tenant.objects.filter(pk=request.data.get('tenant')).first()
        if not tenant:
            return Response({'error': 'Choose the ISP'}, status=400)
        try:
            s = create(tenant, request.data.get('amount') or None, actor=request.user)
        except SettlementError as e:
            return Response({'error': str(e)}, status=400)
        return Response(SettlementSerializer(s).data, status=201)


class SettlementActionView(APIView):
    """POST {action: approve | cancel | retry}"""
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        from cloud.billing import settlement as svc
        s = Settlement.objects.filter(pk=pk).select_related('tenant').first()
        if not s:
            return Response(status=404)
        action = request.data.get('action')
        try:
            if action == 'approve':
                svc.approve(s, request.user)
            elif action == 'cancel':
                svc.cancel(s, request.user)
            elif action == 'retry':
                if s.status != 'failed':
                    return Response({'error': 'Only failed payouts can be retried'}, status=400)
                s = svc.create(s.tenant, s.amount, actor=request.user)
            else:
                return Response({'error': 'Unknown action'}, status=400)
        except svc.SettlementError as e:
            return Response({'error': str(e)}, status=400)
        s.refresh_from_db()
        return Response(SettlementSerializer(s).data)


class LedgerView(APIView):
    """GET a tenant's statement; POST {amount, description} an adjustment."""
    permission_classes = [IsPlatform]

    def get(self, request, pk):
        tenant = Tenant.objects.filter(pk=pk).first()
        if not tenant:
            return Response(status=404)
        return statement(request, tenant)

    def post(self, request, pk):
        import secrets
        from decimal import Decimal, InvalidOperation
        from cloud.billing.ledger import post
        from cloud.tenants.services import log
        if not request.user.is_platform_admin:
            return Response({'error': 'Platform admins only.'}, status=403)
        tenant = Tenant.objects.filter(pk=pk).first()
        if not tenant:
            return Response(status=404)
        try:
            amount = Decimal(str(request.data.get('amount')))
        except (InvalidOperation, TypeError):
            return Response({'error': 'Enter an amount (negative to deduct)'}, status=400)
        reason = (request.data.get('description') or '').strip()
        if not amount or not reason:
            return Response({'error': 'An amount and a reason are both required'}, status=400)
        entry, _ = post(tenant, 'adjustment', amount, f'adj-{secrets.token_hex(6)}', reason)
        entry.created_by = request.user
        entry.save(update_fields=['created_by'])
        log(tenant, 'billing', f'Ledger adjustment KES {amount:,.2f}: {reason}', actor=request.user)
        return Response(LedgerSerializer(entry).data, status=201)


def statement(request, tenant):
    from cloud.billing.ledger import balance
    from cloud.billing.settlement import available
    qs = _dates(LedgerEntry.objects.filter(tenant=tenant).select_related('created_by'), request, 'created_at')
    if request.query_params.get('export') == 'csv':
        return csv_response(f'statement-{tenant.slug}', ['Date', 'Type', 'Amount', 'Reference', 'Description'],
                            [[timezone.localtime(e.created_at).strftime('%Y-%m-%d %H:%M'), e.get_kind_display(), e.amount,
                              e.reference, e.description] for e in qs[:50000]])
    resp = paginate(request, qs, LedgerSerializer)
    resp.data['balance'] = str(balance(tenant))
    resp.data['available'] = str(available(tenant))
    return resp


# --- ISP owner portal -------------------------------------------------------------

class PortalInvoicesView(APIView):
    permission_classes = [IsTenantOwner]

    def get(self, request):
        return paginate(request, Invoice.objects.filter(tenant=request.user.tenant).exclude(status='void'), InvoiceSerializer)


class PortalPayInvoiceView(APIView):
    """STK push to the owner's phone for an unpaid invoice."""
    permission_classes = [IsTenantOwner]

    def post(self, request, pk):
        from cloud.billing import daraja
        inv = Invoice.objects.filter(pk=pk, tenant=request.user.tenant, status='open').first()
        if not inv:
            return Response({'error': 'Invoice not found or already paid'}, status=404)
        cfg = PlatformSettings.load()
        try:
            phone = daraja.normalize_phone(request.data.get('phone') or request.user.phone or inv.tenant.contact_phone)
            resp = daraja.Daraja(cfg).stk_push(phone, inv.amount, inv.number, 'Platform fee',
                                               cfg.public_url(f'/api/mpesa/platform/{cfg.c2b_secret}/'))
        except daraja.DarajaError as e:
            return Response({'error': str(e)}, status=400)
        PlatformPayment.objects.create(invoice=inv, phone=phone, amount=inv.amount,
                                       checkout_request_id=resp.get('CheckoutRequestID', ''))
        return Response({'ok': True, 'message': 'Check your phone and enter your M-Pesa PIN.'})


class PortalStatementView(APIView):
    permission_classes = [IsTenantOwner]

    def get(self, request):
        return statement(request, request.user.tenant)


class PortalSettlementsView(APIView):
    permission_classes = [IsTenantOwner]

    def get(self, request):
        return paginate(request, Settlement.objects.filter(tenant=request.user.tenant), SettlementSerializer)

    def post(self, request):
        """The ISP asks for a payout now (still needs platform approval if that's on)."""
        from cloud.billing.settlement import SettlementError, create
        try:
            s = create(request.user.tenant, request.data.get('amount') or None, actor=request.user)
        except SettlementError as e:
            return Response({'error': str(e)}, status=400)
        return Response(SettlementSerializer(s).data, status=201)


class PortalCollectionsView(APIView):
    permission_classes = [IsTenantOwner]

    def get(self, request):
        qs = _dates(Collection.objects.filter(tenant=request.user.tenant), request, 'paid_at')
        resp = paginate(request, qs, CollectionSerializer)
        resp.data['total_amount'] = qs.filter(verified=True).aggregate(s=Sum('amount'))['s'] or 0
        return resp
