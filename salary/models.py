from django.conf import settings
from django.db import models

from core.models import ActiveManager, CoreModel


class SalarySetting(CoreModel):
    """Per-employee salary rules. One active config per employee.

    Convention: base_monthly_salary is the gross paid when ALL working days
    (6-day week) are present. Deductions apply per absent day; incentives
    apply only on sessions that exceed the weekly target.
    """

    employee = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='salary_setting',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )
    base_monthly_salary = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Salary if 6-day week is fully attended (base for the month)',
    )
    deduction_per_absent_day = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Amount cut from base for every absent working day (half-days = half this)',
    )
    sessions_target_per_week = models.PositiveIntegerField(
        default=0,
        help_text='Sessions per week considered "as expected". 0 = no target',
    )
    incentive_per_extra_session = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Bonus added for each session beyond the weekly target (summed across weeks in the month)',
    )
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['employee__first_name', 'employee__last_name']

    def __str__(self):
        return f"Salary config — {self.employee}"


class MonthlySalary(CoreModel):
    """Computed salary snapshot for one (employee, month). Auto-refreshed."""

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='monthly_salaries',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )
    month = models.DateField(help_text='First day of the salary month')

    total_working_days = models.PositiveIntegerField(default=0)
    present_days = models.PositiveIntegerField(default=0)
    half_days = models.PositiveIntegerField(default=0)
    absent_days = models.PositiveIntegerField(default=0)
    total_sessions = models.PositiveIntegerField(default=0)
    extra_sessions = models.PositiveIntegerField(
        default=0,
        help_text='Sessions beyond the weekly target across all weeks of the month',
    )

    base_monthly_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deduction = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    incentive = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    in_hand_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    generated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-month', 'employee__first_name']
        unique_together = ('employee', 'month')

    def __str__(self):
        return f"{self.employee} — {self.month:%b %Y} → ₹{self.in_hand_salary}"
