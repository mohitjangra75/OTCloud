from django.contrib import admin

from salary.models import MonthlySalary, SalarySetting


@admin.register(SalarySetting)
class SalarySettingAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'base_monthly_salary', 'deduction_per_absent_day',
        'sessions_target_per_week', 'incentive_per_extra_session', 'updated_at',
    ]
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__mobile_number']
    list_per_page = 30


@admin.register(MonthlySalary)
class MonthlySalaryAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'month', 'total_working_days', 'present_days',
        'absent_days', 'half_days', 'total_sessions', 'extra_sessions',
        'base_monthly_salary', 'deduction', 'incentive', 'in_hand_salary',
    ]
    list_filter = ['month']
    search_fields = ['employee__first_name', 'employee__last_name']
    date_hierarchy = 'month'
    list_per_page = 30
