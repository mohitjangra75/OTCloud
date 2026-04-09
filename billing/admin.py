from django.contrib import admin
from billing.models import Invoice, InvoiceItem


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ['date', 'description', 'amount', 'appointment', 'is_active']
    readonly_fields = []


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number', 'client', 'total_amount', 'paid_amount',
        'status', 'due_date', 'created_at',
    ]
    list_filter = ['status', 'created_at']
    search_fields = ['invoice_number', 'client__first_name', 'client__last_name']
    readonly_fields = ['invoice_number', 'total_amount', 'paid_amount', 'created_at', 'updated_at']
    inlines = [InvoiceItemInline]
    list_per_page = 20


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'date', 'description', 'amount']
    list_filter = ['date']
    search_fields = ['description', 'invoice__invoice_number']
    list_per_page = 20
