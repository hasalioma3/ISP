from django.core.validators import FileExtensionValidator
from django.db import models

from apps.customers.models import Customer


class InventoryItem(models.Model):
    """
    A stock keeping unit (router, cable, connector, etc). current_stock is
    never stored directly -- it's always (total purchased - total used),
    computed fresh from the purchase/usage ledgers below, so it can never
    drift out of sync with what actually happened (the same reasoning as
    apps.accounting's ledger-based approach to money).
    """
    CATEGORY_CHOICES = [
        ('router', 'Router / CPE'),
        ('antenna', 'Antenna'),
        ('cable', 'Cable'),
        ('connector', 'Connector'),
        ('mounting', 'Mounting Hardware'),
        ('power', 'Power Supply / PoE'),
        ('switch', 'Switch'),
        ('fiber', 'Fiber Optic Equipment'),
        ('tool', 'Tools'),
        ('other', 'Other'),
    ]
    UNIT_CHOICES = [
        ('piece', 'Piece'),
        ('meter', 'Meter'),
        ('box', 'Box'),
        ('roll', 'Roll'),
        ('pair', 'Pair'),
    ]

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='piece')
    sku = models.CharField(max_length=50, blank=True)
    # Below this quantity in storage, the item counts as low stock.
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_items'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def total_purchased(self):
        return self.purchases.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def total_used(self):
        return self.usages.aggregate(total=models.Sum('quantity'))['total'] or 0

    @property
    def current_stock(self):
        return self.total_purchased - self.total_used

    @property
    def is_low_stock(self):
        return self.current_stock <= self.reorder_level


class InventoryPurchase(models.Model):
    """
    Stock-in -- what was bought. Each purchase automatically creates a
    linked apps.accounting.Expense (category='equipment') so the profit
    dashboard reflects real inventory cost without double data entry --
    see InventoryPurchaseViewSet, which keeps the two in sync on
    create/update/delete.
    """
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='purchases')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    supplier = models.CharField(max_length=150, blank=True)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_purchases_recorded'
    )
    linked_expense = models.ForeignKey(
        'accounting.Expense', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_purchase'
    )
    notes = models.TextField(blank=True)
    # Receipt/invoice for this purchase.
    attachment = models.FileField(
        upload_to='inventory/purchases/%Y/%m/', blank=True, null=True,
        validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png', 'heic'])]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_purchases'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.quantity} x {self.item.name} ({self.date})"

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost


class InventoryUsage(models.Model):
    """
    Stock-out -- what was used, on which customer, and why. customer is
    mandatory: usage not tied to a real billing customer (tower/internal
    equipment, office setup) goes against a dedicated internal-use
    Customer account instead of a free-text fallback, so every usage
    record has a real, reportable owner.
    """
    REASON_CHOICES = [
        ('new_install', 'New Install'),
        ('repair', 'Repair'),
        ('migration', 'Migration'),
        ('office_setup', 'Office Setup'),
        ('other', 'Other'),
    ]

    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='usages')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT,
        related_name='inventory_used_on'
    )
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    date = models.DateField()
    recorded_by = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_usages_recorded'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_usages'
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.quantity} x {self.item.name} used on {self.customer.username} ({self.get_reason_display()}, {self.date})"
