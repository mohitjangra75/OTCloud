from django.contrib import admin

from attendance.models import AttendanceLog


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = (
        'user',
        'date',
        'check_in_time',
        'check_out_time',
        'duration',
        'is_active',
        'is_deleted',
    )
    list_filter = ('date', 'is_active', 'is_deleted')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    date_hierarchy = 'date'
    readonly_fields = ('id', 'duration', 'created_at', 'updated_at')
    raw_id_fields = ('user', 'created_by', 'updated_by')
    list_per_page = 50

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
