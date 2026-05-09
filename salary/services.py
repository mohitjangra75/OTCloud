from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Sum

from salary.models import MonthlySalary, PerformanceRating, SalarySetting


def first_of_month(d):
    return date(d.year, d.month, 1)


def next_month(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def previous_month(d):
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def working_days_in_month(d):
    """All days in the month except Sunday (weekday == 6) — 6-day week."""
    start = first_of_month(d)
    end = next_month(start)
    count = 0
    cur = start
    one = timedelta(days=1)
    while cur < end:
        if cur.weekday() != 6:
            count += 1
        cur += one
    return count


class SalaryService:
    """
    Salary rules:
      - Base monthly salary = paid in full when 6-day week is fully attended
      - Per-day deduction × absent days (half-days = half this)
      - Performance incentive = sum(rating star scores) × per-rating-point
        (clients rate their assigned therapist each month).

    Sundays are excluded from working_days, present_days, half_days, and
    absent_days — they don't count anywhere.
    """

    @staticmethod
    def get_setting(employee):
        return SalarySetting.active_objects.filter(employee=employee).first()

    @staticmethod
    @transaction.atomic
    def compute(employee, target_date, actor=None):
        from attendance.models import AttendanceLog, AttendanceMark
        from appointments.models import Appointment

        month = first_of_month(target_date)
        month_end = next_month(month)
        today = date.today()

        setting = SalaryService.get_setting(employee)
        base = (setting.base_monthly_salary if setting else Decimal('0')) or Decimal('0')
        deduction_per_day = (
            setting.deduction_per_absent_day if setting else Decimal('0')
        ) or Decimal('0')
        per_rating_point = (
            setting.incentive_per_rating_point if setting else Decimal('0')
        ) or Decimal('0')

        total_working_days = working_days_in_month(month)

        # ---- Attendance counts (Sundays explicitly skipped) ----
        present_dates = set(
            AttendanceLog.active_objects
            .filter(user=employee, date__gte=month, date__lt=month_end)
            .values_list('date', flat=True)
        )
        marks = list(
            AttendanceMark.active_objects
            .filter(user=employee, date__gte=month, date__lt=month_end)
        )
        half_day_dates = {m.date for m in marks if m.status == AttendanceMark.Status.HALF_DAY}
        leave_dates = {m.date for m in marks if m.status == AttendanceMark.Status.LEAVE}

        present_days = 0
        half_days = 0
        absent_days = 0
        cur = month
        one = timedelta(days=1)
        while cur < month_end:
            if cur.weekday() == 6:  # Sunday — skip entirely
                cur += one
                continue
            if cur in half_day_dates:
                half_days += 1
            elif cur in leave_dates:
                absent_days += 1
            elif cur in present_dates:
                present_days += 1
            else:
                if cur <= today:
                    absent_days += 1
            cur += one

        # ---- Sessions completed this month (used for display only) ----
        total_sessions = (
            Appointment.active_objects
            .filter(staff=employee, status=Appointment.Status.COMPLETED,
                    date__gte=month, date__lt=month_end)
            .count()
        )

        # ---- Performance ratings → incentive ----
        ratings = PerformanceRating.active_objects.filter(
            therapist=employee, month=month,
        )
        agg = ratings.aggregate(total_score=Sum('score'), avg=Avg('score'))
        total_score = agg['total_score'] or 0
        avg_rating = Decimal(str(round(agg['avg'] or 0, 2)))
        total_ratings = ratings.count()

        # ---- Money ----
        deduction = (
            deduction_per_day * Decimal(absent_days)
            + (deduction_per_day / Decimal(2)) * Decimal(half_days)
        ).quantize(Decimal('0.01'))
        incentive = (per_rating_point * Decimal(total_score)).quantize(Decimal('0.01'))
        in_hand = (base - deduction + incentive).quantize(Decimal('0.01'))
        if in_hand < 0:
            in_hand = Decimal('0')

        snap, _ = MonthlySalary.objects.update_or_create(
            employee=employee, month=month,
            defaults={
                'total_working_days': total_working_days,
                'present_days': present_days,
                'half_days': half_days,
                'absent_days': absent_days,
                'total_sessions': total_sessions,
                'total_ratings': total_ratings,
                'avg_rating': avg_rating,
                'base_monthly_salary': base,
                'deduction': deduction,
                'incentive': incentive,
                'in_hand_salary': in_hand,
                'updated_by': actor,
                'is_deleted': False,
            },
        )
        return snap

    @staticmethod
    def compute_all(target_date, actor=None):
        from accounts.models import User
        employees = User.objects.filter(
            role__in=[User.Role.STAFF, User.Role.ADMIN], is_active=True,
        ).order_by('first_name', 'last_name')
        return [SalaryService.compute(e, target_date, actor=actor) for e in employees]

    @staticmethod
    def get_month(target_date, employee=None):
        month = first_of_month(target_date)
        qs = (MonthlySalary.active_objects
              .filter(month=month)
              .select_related('employee')
              .order_by('employee__first_name', 'employee__last_name'))
        if employee:
            qs = qs.filter(employee=employee)
        return qs


class RatingService:
    """Operations on PerformanceRating."""

    @staticmethod
    @transaction.atomic
    def upsert(client, therapist, target_date, score, feedback='', actor=None):
        month = first_of_month(target_date)
        rating, _ = PerformanceRating.objects.update_or_create(
            client=client, therapist=therapist, month=month,
            defaults={
                'score': int(score),
                'feedback': feedback or '',
                'updated_by': actor,
                'is_deleted': False,
            },
        )
        # Refresh the salary snapshot so the new incentive flows immediately
        SalaryService.compute(therapist, month, actor=actor)
        return rating

    @staticmethod
    def for_therapist_month(therapist, target_date):
        return (PerformanceRating.active_objects
                .filter(therapist=therapist, month=first_of_month(target_date))
                .select_related('client')
                .order_by('-score', 'client__first_name'))

    @staticmethod
    def for_client_month(client, target_date):
        return (PerformanceRating.active_objects
                .filter(client=client, month=first_of_month(target_date))
                .select_related('therapist')
                .order_by('-score'))
