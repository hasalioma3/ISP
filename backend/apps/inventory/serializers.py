from rest_framework import serializers

from .models import InventoryItem, InventoryPurchase, InventoryUsage


class InventoryItemSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)
    current_stock = serializers.ReadOnlyField()
    is_low_stock = serializers.ReadOnlyField()

    class Meta:
        model = InventoryItem
        fields = '__all__'


class InventoryPurchaseSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    total_cost = serializers.ReadOnlyField()

    class Meta:
        model = InventoryPurchase
        fields = '__all__'
        read_only_fields = ['recorded_by', 'linked_expense', 'created_at']


class InventoryUsageSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    customer_username = serializers.CharField(source='customer.username', read_only=True, default=None)
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)

    class Meta:
        model = InventoryUsage
        fields = '__all__'
        read_only_fields = ['recorded_by', 'created_at']

    def validate(self, data):
        item = data.get('item') or (self.instance.item if self.instance else None)
        quantity = data.get('quantity', self.instance.quantity if self.instance else None)

        if item is not None and quantity is not None:
            available = item.current_stock
            if self.instance and self.instance.item_id == item.id:
                # Editing an existing record: its own current quantity is
                # already "removed" from stock, so add it back before
                # checking whether the new quantity fits.
                available += self.instance.quantity
            if quantity > available:
                raise serializers.ValidationError(
                    f"Only {available} {item.get_unit_display().lower()}(s) of {item.name} in storage -- can't use {quantity}."
                )

        return data
