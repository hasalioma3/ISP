from decimal import Decimal, ROUND_HALF_UP

from django.db import models

SERVICE_TYPES = ['pppoe', 'hotspot', 'static']


def money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class PricingPlan(models.Model):
    """
    What an ISP pays the platform each month, driven by its subscriber count.

    Count: which subscribers (service types, active-only or all accounts)
    and how the month's counts are combined (peak, average or latest).
    Price: base fee + tiers on the subscribers above `included_subscribers`.
      graduated -- each tier prices only the subscribers inside it
                   (first 100 at 20, the next 400 at 15, ...)
      volume    -- the tier the total falls in prices every subscriber
                   (480 subscribers -> all 480 at 15)
    Then clamped to the minimum/maximum charge.
    """
    COUNT_BASIS = [('active', 'Subscribers with an active plan'), ('all', 'All subscriber accounts')]
    COUNT_METHODS = [('peak', 'Highest count in the month'), ('average', 'Average over the month'),
                     ('latest', 'Count at the end of the month')]
    TIER_MODES = [('graduated', 'Graduated'), ('volume', 'Volume')]

    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True, help_text='Offered on the sign-up page and to ISPs')
    is_default = models.BooleanField(default=False, help_text='Given to new sign-ups that pick nothing')
    sort_order = models.PositiveSmallIntegerField(default=0)

    count_basis = models.CharField(max_length=10, choices=COUNT_BASIS, default='active')
    service_types = models.CharField(max_length=50, default='pppoe,hotspot,static')
    count_method = models.CharField(max_length=10, choices=COUNT_METHODS, default='peak')

    tier_mode = models.CharField(max_length=10, choices=TIER_MODES, default='graduated')
    base_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    included_subscribers = models.PositiveIntegerField(default=0)
    minimum_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    maximum_charge = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    prorate_first_period = models.BooleanField(default=True)

    # Blank = use the platform defaults (Settings -> Settlements).
    collection_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    settlement_fee_flat = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pricing_plans'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def service_type_list(self):
        return [s for s in self.service_types.split(',') if s in SERVICE_TYPES]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            PricingPlan.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)

    @classmethod
    def default(cls):
        return cls.objects.filter(is_active=True, is_default=True).first() or cls.objects.filter(is_active=True).first()

    def quote(self, count, tiers=None):
        """Charge for `count` counted subscribers -> {'amount', 'lines': [...]}."""
        tiers = list(tiers if tiers is not None else self.tiers.all())
        tiers.sort(key=lambda t: (t.up_to is None, t.up_to or 0))
        lines = []
        if self.base_fee:
            lines.append({'label': 'Base fee', 'quantity': 1, 'unit_price': str(money(self.base_fee)),
                          'amount': str(money(self.base_fee))})
        billable = max(0, int(count) - self.included_subscribers)
        if self.included_subscribers:
            lines.append({'label': f'First {self.included_subscribers} subscribers included',
                          'quantity': min(int(count), self.included_subscribers), 'unit_price': '0.00', 'amount': '0.00'})
        total = money(self.base_fee)
        if self.tier_mode == 'volume':
            tier = next((t for t in tiers if t.up_to is None or billable <= t.up_to), tiers[-1] if tiers else None)
            if tier and billable:
                amount = money(tier.unit_price * billable + tier.flat_fee)
                lines.append({'label': f'{billable} subscribers at {money(tier.unit_price)}'
                                       + (f' + {money(tier.flat_fee)} flat' if tier.flat_fee else ''),
                              'quantity': billable, 'unit_price': str(money(tier.unit_price)), 'amount': str(amount)})
                total += amount
        else:
            lower = 0
            for tier in tiers:
                upper = tier.up_to if tier.up_to is not None else max(billable, lower)
                units = max(0, min(billable, upper) - lower)
                if units:
                    amount = money(tier.unit_price * units + tier.flat_fee)
                    label = (f'Subscribers {lower + 1 + self.included_subscribers}-'
                             f'{lower + units + self.included_subscribers} at {money(tier.unit_price)}')
                    lines.append({'label': label + (f' + {money(tier.flat_fee)} flat' if tier.flat_fee else ''),
                                  'quantity': units, 'unit_price': str(money(tier.unit_price)), 'amount': str(amount)})
                    total += amount
                if tier.up_to is None or billable <= upper:
                    break
                lower = upper
        if self.minimum_charge and total < self.minimum_charge:
            lines.append({'label': f'Minimum monthly charge ({money(self.minimum_charge)})', 'quantity': 1,
                          'unit_price': str(money(self.minimum_charge - total)), 'amount': str(money(self.minimum_charge - total))})
            total = money(self.minimum_charge)
        if self.maximum_charge is not None and total > self.maximum_charge:
            lines.append({'label': f'Capped at {money(self.maximum_charge)}', 'quantity': 1,
                          'unit_price': str(money(self.maximum_charge - total)), 'amount': str(money(self.maximum_charge - total))})
            total = money(self.maximum_charge)
        return {'count': int(count), 'billable': billable, 'amount': str(money(total)), 'lines': lines}


class PricingTier(models.Model):
    plan = models.ForeignKey(PricingPlan, on_delete=models.CASCADE, related_name='tiers')
    up_to = models.PositiveIntegerField(null=True, blank=True, help_text='Upper bound of billable subscribers; blank = no limit')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    flat_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))

    class Meta:
        db_table = 'pricing_tiers'
        ordering = ['plan', models.F('up_to').asc(nulls_last=True)]

    def __str__(self):
        return f'{self.plan}: up to {self.up_to or "∞"} @ {self.unit_price}'
