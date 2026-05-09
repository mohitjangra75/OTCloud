from django.conf import settings
from django.db import models

from core.models import ActiveManager, CoreModel


class SalarySetting(CoreModel):
    """Per-employee salary rules. One active config per employee.

    Convention: base_monthly_salary is the gross paid when ALL working days
    (6-day week) are present. Deductions apply per absent day; incentive is
    based on the average client rating received that month.
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
    incentive_per_rating_point = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Bonus per rating star received from clients '
                  '(e.g., ₹100/point → 5★ rating = ₹500 bonus). '
                  'Total = sum of stars across all client ratings × this value.',
    )
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['employee__first_name', 'employee__last_name']

    def __str__(self):
        return f"Salary config — {self.employee}"


class PerformanceRating(CoreModel):
    """A client's monthly rating of their assigned therapist's performance.

    One rating per (client, therapist, month). Drives the rating-based
    incentive paid out in the monthly salary.
    """
    SCORE_CHOICES = [
        (1, '1★ Poor'),
        (2, '2★ Below Average'),
        (3, '3★ Average'),
        (4, '4★ Good'),
        (5, '5★ Excellent'),
    ]

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='ratings_given',
    )
    therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ratings_received',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )
    month = models.DateField(help_text='First day of the rated month')
    score = models.PositiveSmallIntegerField(choices=SCORE_CHOICES)
    feedback = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-month', 'therapist__first_name']
        unique_together = ('client', 'therapist', 'month')

    def __str__(self):
        return f"{self.client} → {self.therapist} | {self.month:%b %Y} | {self.score}★"


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

    total_ratings = models.PositiveIntegerField(
        default=0,
        help_text='Number of client ratings received this month',
    )
    avg_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        help_text='Average rating across all client feedback this month (0–5)',
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
