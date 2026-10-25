from rest_framework import serializers

from .models import Expense, OtherIncome


class ExpenseSerializer(serializers.ModelSerializer):
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Expense
        fields = '__all__'
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']


class OtherIncomeSerializer(serializers.ModelSerializer):
    recorded_by_username = serializers.CharField(source='recorded_by.username', read_only=True, default=None)
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = OtherIncome
        fields = '__all__'
        read_only_fields = ['recorded_by', 'created_at', 'updated_at']
