from django.contrib import admin

from salary.models import MonthlySalary, PerformanceRating, SalarySetting


@admin.register(SalarySetting)
class SalarySettingAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'base_monthly_salary', 'deduction_per_absent_day',
        'incentive_per_rating_point', 'updated_at',
    ]
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__mobile_number']
    list_per_page = 30


@admin.register(MonthlySalary)
class MonthlySalaryAdmin(admin.ModelAdmin):
    list_display = [
        'employee', 'month', 'total_working_days', 'present_days',
        'absent_days', 'half_days', 'total_sessions',
        'total_ratings', 'avg_rating',
        'base_monthly_salary', 'deduction', 'incentive', 'in_hand_salary',
    ]
    list_filter = ['month']
    search_fields = ['employee__first_name', 'employee__last_name']
    date_hierarchy = 'month'
    list_per_page = 30


@admin.register(PerformanceRating)
class PerformanceRatingAdmin(admin.ModelAdmin):
    list_display = ['therapist', 'client', 'month', 'score', 'updated_at']
    list_filter = ['month', 'score']
    search_fields = [
        'therapist__first_name', 'therapist__last_name',
        'client__first_name', 'client__last_name',
        'feedback',
    ]
    date_hierarchy = 'month'
    list_per_page = 30
