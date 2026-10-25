from django.contrib import admin

from .models import Expense, OtherIncome


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'category', 'description', 'amount', 'recorded_by']
    list_filter = ['category', 'date']
    search_fields = ['description', 'notes']


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = ['date', 'category', 'description', 'amount', 'recorded_by']
    list_filter = ['category', 'date']
    search_fields = ['description', 'notes']
