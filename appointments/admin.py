from django.contrib import admin

from appointments.models import Appointment, TherapyType


@admin.register(TherapyType)
class TherapyTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_30', 'price_60', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'client',
        'staff',
        'therapy_type',
        'duration_minutes',
        'session_price',
        'date',
        'start_time',
        'end_time',
        'status',
        'is_active',
        'created_at',
    )
    list_filter = ('status', 'therapy_type', 'duration_minutes', 'is_active', 'is_deleted', 'date', 'staff')
    search_fields = (
        'client__first_name',
        'client__last_name',
        'client__mobile_number',
        'staff__first_name',
        'staff__last_name',
    )
    readonly_fields = ('id', 'session_price', 'created_at', 'updated_at', 'created_by', 'updated_by')
    raw_id_fields = ('client', 'staff')
    date_hierarchy = 'date'
    ordering = ('-date', '-start_time')
