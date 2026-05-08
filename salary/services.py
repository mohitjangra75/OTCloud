from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from salary.models import MonthlySalary, SalarySetting


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
    """All days in the month except Sunday (weekday == 6)."""
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
      - Per-extra-session incentive × sessions exceeding the weekly target
        (summed week-by-week within the month)
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
        weekly_target = (setting.sessions_target_per_week if setting else 0) or 0
        per_extra_amount = (
            setting.incentive_per_extra_session if setting else Decimal('0')
        ) or Decimal('0')

        total_working_days = working_days_in_month(month)

        # ---- Attendance counts ----
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
            if cur.weekday() != 6:  # Sunday off
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

        # ---- Sessions per ISO week (so excess accumulates by week, not month) ----
        session_dates = list(
            Appointment.active_objects
            .filter(staff=employee, status=Appointment.Status.COMPLETED,
                    date__gte=month, date__lt=month_end)
            .values_list('date', flat=True)
        )
        per_week = defaultdict(int)
        for d in session_dates:
            iso_year, iso_week, _ = d.isocalendar()
            per_week[(iso_year, iso_week)] += 1
        total_sessions = sum(per_week.values())

        if weekly_target > 0:
            extra_sessions = sum(max(0, n - weekly_target) for n in per_week.values())
        else:
            extra_sessions = 0  # No target means no incentive payout

        # ---- Money ----
        deduction = (
            deduction_per_day * Decimal(absent_days)
            + (deduction_per_day / Decimal(2)) * Decimal(half_days)
        ).quantize(Decimal('0.01'))
        incentive = (per_extra_amount * Decimal(extra_sessions)).quantize(Decimal('0.01'))
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
                'extra_sessions': extra_sessions,
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
