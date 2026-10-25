from django.core.validators import FileExtensionValidator
from django.db import models

from apps.customers.models import Customer

ATTACHMENT_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'heic']


class Expense(models.Model):
    """
    A cost recorded outside the normal customer-billing flow -- salaries,
    rent, bandwidth/uplink, equipment, etc. Feeds the profit dashboard
    alongside Transaction (customer revenue) and OtherIncome.
    """
    CATEGORY_CHOICES = [
        ('salaries', 'Salaries & Wages'),
        ('rent', 'Rent'),
        ('bandwidth', 'Bandwidth / Uplink'),
        ('equipment', 'Equipment & Hardware'),
        ('maintenance', 'Maintenance & Repairs'),
        ('fuel', 'Fuel / Generator'),
        ('transport', 'Transport'),
        ('marketing', 'Marketing'),
        ('licenses', 'Licenses & Permits'),
        ('utilities', 'Utilities'),
        ('other', 'Other'),
    ]

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expenses_recorded'
    )
    notes = models.TextField(blank=True)
    # Receipt/invoice for this expense.
    attachment = models.FileField(
        upload_to='accounting/expenses/%Y/%m/', blank=True, null=True,
        validators=[FileExtensionValidator(ATTACHMENT_EXTENSIONS)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenses'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_category_display()} - KES {self.amount} ({self.date})"


class OtherIncome(models.Model):
    """
    Income outside the normal customer-billing flow -- equipment sales,
    installation fees, advertising, etc. Feeds the profit dashboard
    alongside Transaction (customer revenue) and Expense.
    """
    CATEGORY_CHOICES = [
        ('equipment_sale', 'Equipment Sale'),
        ('installation_fee', 'Installation Fee'),
        ('advertising', 'Advertising'),
        ('commission', 'Commission'),
        ('refund', 'Refund Received'),
        ('other', 'Other'),
    ]

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='other_income_recorded'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'other_income'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.get_category_display()} - KES {self.amount} ({self.date})"
