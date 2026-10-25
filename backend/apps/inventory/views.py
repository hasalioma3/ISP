from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.models import Expense
from apps.analytics.views import can_see_income
from apps.customers.permissions import RoleAllowed

from .models import InventoryItem, InventoryPurchase, InventoryUsage
from .serializers import InventoryItemSerializer, InventoryPurchaseSerializer, InventoryUsageSerializer


class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    The item catalog. Technicians can see it (they need to know what
    exists to log usage) but not define/edit it -- that's a management
    decision, same split as billing plans.
    """
    serializer_class = InventoryItemSerializer
    queryset = InventoryItem.objects.all()
    filterset_fields = ['category', 'is_active']
    search_fields = ['name', 'sku']
    ordering_fields = ['name', 'category', 'reorder_level']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [RoleAllowed('admin', 'sales', 'technician')()]
        return [RoleAllowed('admin', 'sales')()]


class InventoryPurchaseViewSet(viewsets.ModelViewSet):
    """
    Stock-in. Admin/sales only, same income-visibility convention as
    Expense/OtherIncome -- this is cost data. Each purchase keeps a linked
    Expense (category='equipment') in sync automatically.
    """
    serializer_class = InventoryPurchaseSerializer
    permission_classes = [RoleAllowed('admin', 'sales')]
    queryset = InventoryPurchase.objects.select_related('item')
    filterset_fields = ['item']
    search_fields = ['supplier', 'notes']
    ordering_fields = ['date', 'created_at']

    def _expense_fields(self, purchase):
        return {
            'category': 'equipment',
            'description': f"Inventory purchase: {purchase.quantity} {purchase.item.get_unit_display().lower()}(s) of {purchase.item.name}",
            'amount': purchase.total_cost,
            'date': purchase.date,
            'recorded_by': purchase.recorded_by,
            'notes': f"Supplier: {purchase.supplier}" if purchase.supplier else '',
        }

    def perform_create(self, serializer):
        purchase = serializer.save(recorded_by=self.request.user)
        expense = Expense.objects.create(**self._expense_fields(purchase))
        purchase.linked_expense = expense
        purchase.save(update_fields=['linked_expense'])

    def perform_update(self, serializer):
        purchase = serializer.save()
        if purchase.linked_expense:
            fields = self._expense_fields(purchase)
            fields.pop('recorded_by', None)  # don't reattribute who recorded it on an edit
            for key, value in fields.items():
                setattr(purchase.linked_expense, key, value)
            purchase.linked_expense.save()

    def perform_destroy(self, instance):
        if instance.linked_expense:
            instance.linked_expense.delete()
        instance.delete()


class InventoryUsageViewSet(viewsets.ModelViewSet):
    """
    Stock-out. Technicians can log what they used in the field and on
    whom, but only admin/sales can edit/delete usage history afterwards.
    """
    serializer_class = InventoryUsageSerializer
    queryset = InventoryUsage.objects.select_related('item', 'customer')
    filterset_fields = ['item', 'customer', 'reason']
    search_fields = ['notes']
    ordering_fields = ['date', 'created_at']

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [RoleAllowed('admin', 'sales')()]
        return [RoleAllowed('admin', 'sales', 'technician')()]

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class InventoryDashboardView(APIView):
    """
    Stock levels and what's running low. Open to technicians (operational,
    not financial) but purchase-cost figures are stripped out for them,
    same as revenue elsewhere in this app.
    """
    permission_classes = [RoleAllowed('admin', 'sales', 'technician')]

    def get(self, request):
        show_cost = can_see_income(request.user)
        items = InventoryItem.objects.filter(is_active=True)

        rows = []
        low_stock = []
        for item in items:
            row = {
                'id': item.id,
                'name': item.name,
                'category': item.category,
                'category_display': item.get_category_display(),
                'unit': item.unit,
                'unit_display': item.get_unit_display(),
                'current_stock': item.current_stock,
                'reorder_level': item.reorder_level,
                'is_low_stock': item.is_low_stock,
            }
            rows.append(row)
            if row['is_low_stock']:
                low_stock.append(row)

        response_data = {
            'items': rows,
            'low_stock_items': low_stock,
            'total_items': items.count(),
            'low_stock_count': len(low_stock),
        }

        if show_cost:
            total_value = InventoryPurchase.objects.aggregate(
                total=Sum(
                    ExpressionWrapper(F('quantity') * F('unit_cost'), output_field=DecimalField())
                )
            )['total'] or 0
            response_data['total_purchase_value'] = round(float(total_value), 2)

        return Response(response_data)
