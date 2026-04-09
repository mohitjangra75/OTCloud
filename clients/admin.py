from django.contrib import admin

from clients.models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        'first_name',
        'last_name',
        'mobile_number',
        'email',
        'is_active',
        'is_deleted',
        'created_at',
    )
    list_filter = ('is_active', 'is_deleted', 'gender')
    search_fields = ('first_name', 'last_name', 'mobile_number', 'email')
    readonly_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')
    raw_id_fields = ('user',)
    ordering = ('first_name', 'last_name')
