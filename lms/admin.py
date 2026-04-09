from django.contrib import admin
from lms.models import Lead, FollowUp


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    fields = ['follow_up_date', 'status', 'notes']


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['name', 'mobile', 'source', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'source', 'created_at']
    search_fields = ['name', 'mobile', 'email']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [FollowUpInline]
    list_per_page = 20


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ['lead', 'follow_up_date', 'status']
    list_filter = ['status', 'follow_up_date']
    search_fields = ['lead__name', 'notes']
    list_per_page = 20
