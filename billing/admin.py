from django.contrib import admin

from billing.models import Expense, Invoice, MonthlyBill


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'client', 'month', 'total_sessions',
        'total_billed', 'total_paid', 'balance_due', 'generated_at',
    ]
    list_filter = ['month']
    search_fields = ['invoice_number', 'client__first_name', 'client__last_name']
    date_hierarchy = 'month'
    readonly_fields = ['invoice_number', 'generated_at']
    list_per_page = 30


@admin.register(MonthlyBill)
class MonthlyBillAdmin(admin.ModelAdmin):
    list_display = [
        'month', 'client', 'therapy_type', 'sessions_per_week', 'total_sessions',
        'package_amount', 'paid_amount', 'carry_forward', 'status',
    ]
    list_filter = ['status', 'month', 'therapy_type', 'payment_mode']
    search_fields = [
        'client__first_name', 'client__last_name', 'therapy_type__name',
    ]
    date_hierarchy = 'month'
    list_per_page = 30


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        'date', 'category', 'item', 'amount', 'payment_mode',
        'paid_to', 'paid_to_employee', 'status',
    ]
    list_filter = ['category', 'status', 'date', 'payment_mode']
    search_fields = ['item', 'remarks', 'paid_to']
    date_hierarchy = 'date'
    list_per_page = 30
