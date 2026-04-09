from django.contrib import admin

from appointments.models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'client',
        'staff',
        'date',
        'start_time',
        'end_time',
        'status',
        'is_active',
        'is_deleted',
        'created_at',
    )
    list_filter = ('status', 'is_active', 'is_deleted', 'date', 'staff')
    search_fields = (
        'client__first_name',
        'client__last_name',
        'client__mobile_number',
        'staff__first_name',
        'staff__last_name',
    )
    readonly_fields = ('id', 'created_at', 'updated_at', 'created_by', 'updated_by')
    raw_id_fields = ('client', 'staff')
    date_hierarchy = 'date'
    ordering = ('-date', '-start_time')
