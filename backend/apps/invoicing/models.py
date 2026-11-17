from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.notifications.fields import EncryptedCharField

TEMPLATE_CHOICES = [
    ('classic', 'Classic'),
    ('modern', 'Modern'),
    ('minimal', 'Minimal'),
    ('bold', 'Bold'),
    ('compact', 'Compact receipt'),
]


class InvoiceSettings(models.Model):
    """Singleton (pk=1): invoice look, company details, VAT and KRA eTIMS."""
    # --- Design ---
    default_template = models.CharField(max_length=20, choices=TEMPLATE_CHOICES, default='classic')
    accent_color = models.CharField(max_length=7, default='#1f5f3f')
    show_logo = models.BooleanField(default=True)

    # --- Company details printed on the invoice (name/logo come from Branding) ---
    company_pin = models.CharField('KRA PIN', max_length=20, blank=True)
    company_address = models.TextField(blank=True)
    company_email = models.EmailField(blank=True)
    company_phone = models.CharField(max_length=30, blank=True)
    payment_details = models.TextField(blank=True, help_text='How to pay, e.g. Paybill/Till and account')
    footer_note = models.TextField(blank=True, default='Thank you for your business.')
    terms = models.TextField(blank=True)

    # --- Numbering ---
    number_prefix = models.CharField(max_length=12, default='INV-')
    next_number = models.PositiveIntegerField(default=1)
    due_days = models.PositiveSmallIntegerField(default=0, help_text='0 = due on receipt')

    # --- Tax ---
    vat_registered = models.BooleanField(default=False)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('16'))
    # Plan prices are what customers pay, so by default VAT is inside them.
    prices_include_vat = models.BooleanField(default=True)

    # --- Automation ---
    # Make an invoice for every completed PPPoE (and static IP) payment.
    auto_invoice = models.BooleanField(default=False)
    auto_send = models.BooleanField(default=False, help_text='Email the PDF to customers with an email address')

    # --- KRA eTIMS (OSCU) ---
    etims_enabled = models.BooleanField(default=False)
    etims_environment = models.CharField(max_length=10, choices=[('sandbox', 'Sandbox'), ('production', 'Production')],
                                         default='sandbox')
    etims_base_url = models.URLField(blank=True, help_text='Leave blank for the standard KRA URL of the environment')
    etims_branch_id = models.CharField(max_length=3, default='00')
    etims_device_serial = models.CharField(max_length=100, blank=True)
    etims_cmc_key = EncryptedCharField(max_length=500, blank=True)
    etims_initialized_at = models.DateTimeField(null=True, blank=True)
    etims_sdc_id = models.CharField(max_length=60, blank=True)
    etims_mrc_no = models.CharField(max_length=60, blank=True)
    # Signing on: every new invoice is signed. Off: staff sign individually.
    etims_auto_sign = models.BooleanField(default=True)
    etims_item_code = models.CharField(max_length=20, blank=True)
    etims_item_class_code = models.CharField(max_length=10, default='81112100')
    etims_tax_type = models.CharField(max_length=1, default='B', help_text='A exempt, B 16%, C 0%, D non-VAT, E 8%')
    etims_last_invoice_no = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoice_settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Invoice(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('issued', 'Issued'), ('paid', 'Paid'), ('void', 'Void')]
    ETIMS_CHOICES = [('none', 'Not signed'), ('pending', 'Signing'), ('signed', 'Signed'), ('failed', 'Failed'),
                     ('credited', 'Credit note signed')]

    number = models.CharField(max_length=40, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='invoices')
    transaction = models.OneToOneField('billing.Transaction', null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='invoice')
    template = models.CharField(max_length=20, choices=TEMPLATE_CHOICES, default='classic')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='paid')
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)

    # Bill-to, frozen at issue time.
    customer_name = models.CharField(max_length=200)
    customer_pin = models.CharField('Customer KRA PIN', max_length=20, blank=True)
    customer_phone = models.CharField(max_length=30, blank=True)
    customer_email = models.EmailField(blank=True)
    customer_address = models.TextField(blank=True)

    # [{"description", "quantity", "unit_price", "amount"}] -- amounts as
    # entered (VAT-inclusive when the settings say prices include VAT).
    lines = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    payment_ref = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    # KRA eTIMS
    etims_status = models.CharField(max_length=10, choices=ETIMS_CHOICES, default='none')
    etims_invoice_no = models.PositiveIntegerField(null=True, blank=True)
    etims_receipt_no = models.CharField(max_length=40, blank=True)
    etims_total_receipt_no = models.CharField(max_length=40, blank=True)
    etims_internal_data = models.CharField(max_length=200, blank=True)
    etims_signature = models.CharField(max_length=200, blank=True)
    etims_sdc_id = models.CharField(max_length=60, blank=True)
    etims_mrc_no = models.CharField(max_length=60, blank=True)
    etims_signed_at = models.DateTimeField(null=True, blank=True)
    etims_error = models.TextField(blank=True)
    etims_response = models.JSONField(null=True, blank=True)
    credit_note_no = models.PositiveIntegerField(null=True, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices'
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return self.number

    @property
    def balance_due(self):
        return max(Decimal('0'), self.total - self.amount_paid)

    @property
    def etims_qr_url(self):
        if not self.etims_signature:
            return ''
        cfg = InvoiceSettings.load()
        host = 'etims.kra.go.ke' if cfg.etims_environment == 'production' else 'etims-sbx.kra.go.ke'
        return (f'https://{host}/common/link/etims/receipt/indexEtimsReceiptData?Data='
                f'{cfg.company_pin}{cfg.etims_branch_id}{self.etims_signature}')
