from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import Transaction
from apps.customers.models import Customer
from apps.customers.permissions import RoleAllowed
from apps.invoicing import etims, services
from apps.invoicing.models import TEMPLATE_CHOICES, Invoice, InvoiceSettings
from apps.invoicing.pdf import TEMPLATES, render_pdf, sample_invoice


class SettingsSerializer(serializers.ModelSerializer):
    etims_cmc_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    etims_cmc_key_set = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceSettings
        exclude = ['id']
        read_only_fields = ['etims_initialized_at', 'etims_sdc_id', 'etims_mrc_no', 'updated_at']

    def get_etims_cmc_key_set(self, obj):
        return bool(obj.etims_cmc_key)

    def validate_accent_color(self, v):
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', v or ''):
            raise serializers.ValidationError('Use a colour like #1f5f3f')
        return v

    def validate_company_pin(self, v):
        v = (v or '').strip().upper()
        import re
        if v and not re.fullmatch(r'[A-Z]\d{9}[A-Z]', v):
            raise serializers.ValidationError('A KRA PIN looks like P051234567X')
        return v

    def validate_etims_tax_type(self, v):
        if v not in etims.TAX_RATES:
            raise serializers.ValidationError('Use A, B, C, D or E')
        return v

    def update(self, instance, validated):
        # A blank key keeps the stored one (it's never sent back to the browser).
        if not validated.get('etims_cmc_key'):
            validated.pop('etims_cmc_key', None)
        return super().update(instance, validated)


class InvoiceSerializer(serializers.ModelSerializer):
    customer_username = serializers.CharField(source='customer.username', read_only=True)
    customer_service_type = serializers.CharField(source='customer.service_type', read_only=True)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    etims_qr_url = serializers.CharField(read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', default='', read_only=True)

    class Meta:
        model = Invoice
        exclude = ['etims_response']
        read_only_fields = [f.name for f in Invoice._meta.fields if f.name not in
                            ('template', 'customer_name', 'customer_pin', 'customer_phone', 'customer_email',
                             'customer_address', 'notes', 'due_date')]

    def validate_customer_pin(self, v):
        return (v or '').strip().upper()

    def validate(self, attrs):
        inv = self.instance
        if inv and inv.etims_status in ('signed', 'credited'):
            locked = {'customer_name', 'customer_pin'} & set(attrs)
            if any(attrs[f] != getattr(inv, f) for f in locked):
                raise serializers.ValidationError('This invoice is signed with KRA; the name and PIN can no longer change.')
        return attrs


class Pages(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 200


def _pdf_response(invoice, template=None, download=False):
    pdf = render_pdf(invoice, template)
    resp = HttpResponse(pdf, content_type='application/pdf')
    disposition = 'attachment' if download else 'inline'
    resp['Content-Disposition'] = f'{disposition}; filename="{invoice.number}.pdf"'
    return resp


class InvoiceSettingsView(APIView):
    permission_classes = [RoleAllowed('admin')]

    def get(self, request):
        return Response({**SettingsSerializer(InvoiceSettings.load()).data,
                         'templates': [{'key': k, 'label': v} for k, v in TEMPLATE_CHOICES]})

    def put(self, request):
        ser = SettingsSerializer(InvoiceSettings.load(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return self.get(request)

    patch = put


class EtimsActionView(APIView):
    """POST {action: initialize | register_item}."""
    permission_classes = [RoleAllowed('admin')]

    def post(self, request):
        action = request.data.get('action')
        try:
            if action == 'initialize':
                info = etims.initialize()
                return Response({'ok': True, 'message': 'Device initialised with KRA.',
                                 'sdc_id': info.get('sdcId', ''), 'mrc_no': info.get('mrcNo', '')})
            if action == 'register_item':
                code = etims.register_item()
                return Response({'ok': True, 'message': f'Item {code} registered with KRA.', 'item_code': code})
        except etims.EtimsError as e:
            return Response({'ok': False, 'error': str(e)}, status=400)
        return Response({'error': 'Unknown action'}, status=400)


class TemplatePreviewView(APIView):
    """A sample invoice in the chosen design (?template=), as a PDF."""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        inv = sample_invoice()
        return _pdf_response(inv, request.query_params.get('template'))


class InvoiceListView(APIView):
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        qs = Invoice.objects.select_related('customer', 'created_by')
        p = request.query_params
        if p.get('search'):
            s = p['search'].strip()
            qs = qs.filter(Q(number__icontains=s) | Q(customer_name__icontains=s) | Q(customer__username__icontains=s)
                           | Q(payment_ref__icontains=s) | Q(customer_phone__icontains=s))
        for field in ('status', 'etims_status'):
            if p.get(field):
                qs = qs.filter(**{field: p[field]})
        if p.get('customer'):
            qs = qs.filter(customer_id=p['customer'])
        if p.get('from'):
            qs = qs.filter(issue_date__gte=p['from'])
        if p.get('to'):
            qs = qs.filter(issue_date__lte=p['to'])
        pager = Pages()
        page = pager.paginate_queryset(qs, request, view=self)
        return pager.get_paginated_response(InvoiceSerializer(page, many=True).data)

    def post(self, request):
        """A manual invoice: {customer_id, lines:[{description, quantity, unit_price}], status, ...}."""
        customer = get_object_or_404(Customer, pk=request.data.get('customer_id'))
        status_ = request.data.get('status') or 'issued'
        if status_ not in ('issued', 'paid', 'draft'):
            return Response({'error': 'Status must be draft, issued or paid'}, status=400)
        overrides = {k: request.data.get(k) for k in ('customer_name', 'customer_pin', 'customer_address',
                                                      'customer_email', 'customer_phone')}
        if overrides.get('customer_pin'):
            overrides['customer_pin'] = overrides['customer_pin'].strip().upper()
        try:
            inv = services.create_invoice(customer, request.data.get('lines') or [], actor=request.user,
                                          template=request.data.get('template'), status=status_,
                                          notes=request.data.get('notes') or '', overrides=overrides,
                                          sign=request.data.get('sign') if status_ != 'draft' else False)
        except services.InvoiceError as e:
            return Response({'error': str(e)}, status=400)
        return Response(InvoiceSerializer(inv).data, status=201)


class InvoiceFromTransactionView(APIView):
    """POST {transaction_id, template?, customer_pin?, customer_address?, sign?}"""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def post(self, request):
        txn = get_object_or_404(Transaction.objects.select_related('customer', 'subscription__plan'),
                                pk=request.data.get('transaction_id'))
        overrides = {k: request.data.get(k) for k in ('customer_pin', 'customer_address', 'customer_name')}
        if overrides.get('customer_pin'):
            overrides['customer_pin'] = overrides['customer_pin'].strip().upper()
        try:
            inv, created = services.invoice_for_transaction(txn, actor=request.user, template=request.data.get('template'),
                                                            overrides=overrides, sign=request.data.get('sign'))
        except services.InvoiceError as e:
            return Response({'error': str(e)}, status=400)
        return Response({**InvoiceSerializer(inv).data, 'created': created}, status=201 if created else 200)


class InvoiceablePaymentsView(APIView):
    """Recent completed PPPoE/static payments, flagged with their invoice if any."""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request):
        qs = Transaction.objects.filter(status='completed', customer__service_type__in=services.INVOICE_SERVICE_TYPES) \
            .exclude(payment_method='balance').filter(amount__gt=0).select_related('customer', 'subscription__plan', 'invoice')
        s = (request.query_params.get('search') or '').strip()
        if s:
            qs = qs.filter(Q(customer__username__icontains=s) | Q(mpesa_receipt_number__icontains=s)
                           | Q(customer__first_name__icontains=s) | Q(customer__last_name__icontains=s))
        if request.query_params.get('uninvoiced') == '1':
            qs = qs.filter(invoice__isnull=True)
        rows = []
        for t in qs.order_by('-created_at')[:100]:
            inv = getattr(t, 'invoice', None)
            rows.append({
                'id': t.pk, 'created_at': t.created_at, 'amount': str(t.amount), 'method': t.payment_method,
                'receipt': t.mpesa_receipt_number or t.transaction_id, 'customer_id': t.customer_id,
                'username': t.customer.username, 'name': t.customer.get_full_name() or t.customer.username,
                'plan': t.subscription.plan.name if t.subscription_id else '',
                'invoice_id': inv.pk if inv else None, 'invoice_number': inv.number if inv else '',
            })
        return Response(rows)


class InvoiceDetailView(APIView):
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request, pk):
        return Response(InvoiceSerializer(get_object_or_404(Invoice, pk=pk)).data)

    def patch(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        ser = InvoiceSerializer(inv, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class InvoicePdfView(APIView):
    permission_classes = [RoleAllowed('admin', 'sales')]

    def get(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        return _pdf_response(inv, request.query_params.get('template'), request.query_params.get('download') == '1')


class InvoiceActionView(APIView):
    """POST {action: sign | void | send | mark_paid | issue}"""
    permission_classes = [RoleAllowed('admin', 'sales')]

    def post(self, request, pk):
        inv = get_object_or_404(Invoice, pk=pk)
        action = request.data.get('action')
        try:
            if action == 'sign':
                etims.sign(inv)
            elif action == 'void':
                if not (request.user.is_superuser or request.user.role == 'admin'):
                    return Response({'error': 'Only admins can void invoices.'}, status=403)
                services.void(inv, request.user)
            elif action == 'send':
                ok, error = services.send(inv)
                if not ok:
                    return Response({'error': error}, status=400)
            elif action == 'mark_paid':
                if inv.status == 'void':
                    return Response({'error': 'This invoice is void.'}, status=400)
                inv.status, inv.amount_paid = 'paid', inv.total
                inv.payment_ref = (request.data.get('payment_ref') or inv.payment_ref or '')[:100]
                inv.save(update_fields=['status', 'amount_paid', 'payment_ref', 'updated_at'])
            elif action == 'issue':
                if inv.status != 'draft':
                    return Response({'error': 'Only drafts can be issued.'}, status=400)
                inv.status = 'issued'
                inv.save(update_fields=['status', 'updated_at'])
                cfg = InvoiceSettings.load()
                if cfg.etims_enabled and cfg.etims_auto_sign:
                    try:
                        etims.sign(inv)
                    except etims.EtimsError:
                        pass
            else:
                return Response({'error': 'Unknown action'}, status=400)
        except etims.EtimsError as e:
            inv.refresh_from_db()
            return Response({'error': str(e), 'invoice': InvoiceSerializer(inv).data}, status=400)
        inv.refresh_from_db()
        return Response(InvoiceSerializer(inv).data)


class MyInvoicesView(APIView):
    """The signed-in customer's own invoices."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Invoice.objects.filter(customer=request.user).exclude(status='draft')[:100]
        return Response([{'id': i.pk, 'number': i.number, 'issue_date': i.issue_date, 'total': str(i.total),
                          'status': i.status, 'etims_signed': i.etims_status == 'signed',
                          'description': (i.lines[0]['description'] if i.lines else '')} for i in qs])


class MyInvoicePdfView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        inv = get_object_or_404(Invoice.objects.exclude(status='draft'), pk=pk, customer=request.user)
        return _pdf_response(inv, download=request.query_params.get('download') == '1')
