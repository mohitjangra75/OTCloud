"""Role-specific dashboards.

- Admin  → operations overview: today snapshot, revenue, team, pending actions
- Staff  → personal workspace: my hours, my sessions, my upcoming
- Client → client portal: next session, spend, history
"""
import calendar
from collections import OrderedDict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment
from attendance.models import AttendanceLog, AttendanceMark
from billing.models import MonthlyBill
from clients.models import Client
from lms.models import FollowUp, Lead


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

@login_required
def dashboard_view(request):
    user = request.user
    today = timezone.localdate()
    month_start = today.replace(day=1)

    if user.is_superuser or user.role == User.Role.ADMIN:
        ctx = _admin_context(today, month_start)
        template = 'analytics/dashboard_admin.html'
    elif user.role == User.Role.STAFF:
        ctx = _staff_context(user, today, month_start)
        template = 'analytics/dashboard_staff.html'
    else:
        ctx = _client_context(user, today, month_start)
        template = 'analytics/dashboard_client.html'

    ctx['today'] = today
    return render(request, template, ctx)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_duration(td):
    if not td:
        return '0h 0m'
    s = int(td.total_seconds())
    h, m = s // 3600, (s % 3600) // 60
    return f'{h}h {m}m'


def _day_labels(today, n=7):
    """Last n dates ending at today, oldest first."""
    return [today - timedelta(days=i) for i in range(n - 1, -1, -1)]


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

def _admin_context(today, month_start):
    # ---- Today snapshot ----
    today_appointments = Appointment.active_objects.filter(date=today)
    today_total = today_appointments.count()
    today_completed = today_appointments.filter(status=Appointment.Status.COMPLETED).count()
    today_scheduled = today_appointments.filter(status=Appointment.Status.SCHEDULED).count()

    checked_in_now = AttendanceLog.active_objects.filter(
        date=today, check_out_time__isnull=True,
    ).count()

    # Staff on duty vs on leave today
    staff_qs = User.objects.filter(
        role__in=[User.Role.STAFF, User.Role.ADMIN], is_active=True,
    )
    total_staff = staff_qs.count()
    on_leave_today = AttendanceMark.active_objects.filter(
        date=today, status=AttendanceMark.Status.LEAVE,
    ).count()

    # ---- Revenue ----
    month_bills = MonthlyBill.active_objects.filter(month=month_start)
    paid_this_month = month_bills.aggregate(total=Sum('paid_amount'))['total'] or 0

    billed_this_month = month_bills.aggregate(
        billed=Sum('package_amount'), carry=Sum('carry_forward'),
    )
    outstanding_raw = ((billed_this_month['billed'] or 0)
                       + (billed_this_month['carry'] or 0)
                       - (paid_this_month or 0))
    outstanding = outstanding_raw if outstanding_raw > 0 else 0

    overdue_count = month_bills.filter(
        status__in=[MonthlyBill.Status.UNPAID, MonthlyBill.Status.PARTIAL],
    ).count()

    paid_today = MonthlyBill.active_objects.filter(
        paid_date=today,
    ).aggregate(total=Sum('paid_amount'))['total'] or 0

    # ---- 7-day appointment trend (completed per day) ----
    last_7 = _day_labels(today, 7)
    appts_by_day = {
        d['date']: d['n']
        for d in Appointment.active_objects.filter(
            date__gte=last_7[0], date__lte=today,
        ).values('date').annotate(n=Count('id'))
    }
    max_7 = max(appts_by_day.values(), default=1) or 1
    trend_days = [
        {
            'date': d,
            'label': d.strftime('%a'),
            'count': appts_by_day.get(d, 0),
            'pct': int((appts_by_day.get(d, 0) / max_7) * 100),
            'is_today': d == today,
        }
        for d in last_7
    ]

    # ---- Pending actions ----
    pending_reassign_count = Appointment.active_objects.filter(
        needs_reassignment=True, date__gte=today,
    ).count()
    pending_followups = FollowUp.active_objects.filter(
        follow_up_date__date__lte=today, status='pending',
    ).count()

    # ---- Team leaderboard (month) ----
    top_staff = list(staff_qs.exclude(role=User.Role.ADMIN).annotate(
        month_completed=Count(
            'staff_appointments',
            filter=Q(
                staff_appointments__status=Appointment.Status.COMPLETED,
                staff_appointments__date__gte=month_start,
                staff_appointments__date__lte=today,
                staff_appointments__is_deleted=False,
            ),
        ),
        month_hours_raw=Sum(
            'attendance_logs__duration',
            filter=Q(
                attendance_logs__date__gte=month_start,
                attendance_logs__date__lte=today,
                attendance_logs__is_deleted=False,
            ),
        ),
    ).order_by('-month_completed', '-month_hours_raw')[:5])
    for s in top_staff:
        s.month_hours = _fmt_duration(s.month_hours_raw)

    # ---- Upcoming today (next 5) ----
    upcoming_today = (
        today_appointments
        .filter(status=Appointment.Status.SCHEDULED)
        .select_related('client', 'staff', 'therapy_type')
        .order_by('start_time')[:5]
    )

    # ---- Leads mini-funnel ----
    lead_counts = {row['status']: row['n'] for row in Lead.active_objects.values('status').annotate(n=Count('id'))}
    new_leads = lead_counts.get('new', 0)
    contacted_leads = lead_counts.get('contacted', 0)
    interested_leads = lead_counts.get('interested', 0)
    converted_leads = lead_counts.get('converted', 0)
    total_pipeline = new_leads + contacted_leads + interested_leads
    conv_rate = (
        round((converted_leads / (converted_leads + total_pipeline)) * 100)
        if (converted_leads + total_pipeline) else 0
    )

    # ---- Growth ----
    new_clients_month = Client.active_objects.filter(created_at__date__gte=month_start).count()

    return {
        # snapshot
        'today_total': today_total,
        'today_completed': today_completed,
        'today_scheduled': today_scheduled,
        'checked_in_now': checked_in_now,
        'total_staff': total_staff,
        'on_leave_today': on_leave_today,
        # revenue
        'paid_this_month': paid_this_month,
        'paid_today': paid_today,
        'outstanding': outstanding,
        'overdue_count': overdue_count,
        # trend
        'trend_days': trend_days,
        # pending
        'pending_reassign_count': pending_reassign_count,
        'pending_followups': pending_followups,
        # team
        'top_staff': top_staff,
        # upcoming
        'upcoming_today': upcoming_today,
        # leads
        'new_leads': new_leads,
        'contacted_leads': contacted_leads,
        'interested_leads': interested_leads,
        'converted_leads': converted_leads,
        'conv_rate': conv_rate,
        'new_clients_month': new_clients_month,
        'month_label': month_start.strftime('%B %Y'),
    }


# ---------------------------------------------------------------------------
# Staff dashboard
# ---------------------------------------------------------------------------

def _staff_context(user, today, month_start):
    # ---- Today ----
    today_logs = AttendanceLog.active_objects.filter(user=user, date=today).order_by('check_in_time')
    today_duration = sum(
        (l.duration for l in today_logs if l.duration),
        timedelta(),
    )
    active_session = today_logs.filter(check_out_time__isnull=True).first()

    today_mark = AttendanceMark.active_objects.filter(user=user, date=today).first()

    todays_appts = (
        Appointment.active_objects.filter(staff=user, date=today)
        .exclude(status=Appointment.Status.CANCELLED)
        .select_related('client', 'therapy_type')
        .order_by('start_time')
    )

    # ---- Month ----
    month_logs = AttendanceLog.active_objects.filter(
        user=user, date__gte=month_start, date__lte=today,
    )
    month_duration = month_logs.aggregate(total=Sum('duration'))['total'] or timedelta()
    month_days_checked_in = month_logs.values('date').distinct().count()

    # Expected workdays month-to-date (Mon–Sat)
    expected = 0
    d = month_start
    while d <= today:
        if d.weekday() != 6:
            expected += 1
        d = d + timedelta(days=1)
    attendance_pct = round((month_days_checked_in / expected) * 100) if expected else 0

    month_completed_sessions = Appointment.active_objects.filter(
        staff=user, status=Appointment.Status.COMPLETED,
        date__gte=month_start, date__lte=today,
    ).count()

    # ---- 7-day hours ----
    last_7 = _day_labels(today, 7)
    daily_hours = {d: timedelta() for d in last_7}
    for log in AttendanceLog.active_objects.filter(
        user=user, date__gte=last_7[0], date__lte=today,
    ):
        if log.duration and log.date in daily_hours:
            daily_hours[log.date] += log.duration
    max_seconds = max((td.total_seconds() for td in daily_hours.values()), default=1) or 1
    hours_trend = [
        {
            'date': d,
            'label': d.strftime('%a'),
            'display': _fmt_duration(daily_hours[d]),
            'pct': int((daily_hours[d].total_seconds() / max_seconds) * 100),
            'is_today': d == today,
        }
        for d in last_7
    ]

    # ---- Upcoming 5 appointments ----
    upcoming = (
        Appointment.active_objects.filter(
            staff=user, status=Appointment.Status.SCHEDULED, date__gte=today,
        )
        .select_related('client', 'therapy_type')
        .order_by('date', 'start_time')[:5]
    )

    # ---- Planned absences (next 7 days) ----
    upcoming_marks = list(
        AttendanceMark.active_objects.filter(
            user=user, date__gte=today, date__lte=today + timedelta(days=7),
        ).order_by('date')
    )

    return {
        'today_duration_display': _fmt_duration(today_duration),
        'today_sessions_count': today_logs.count(),
        'active_session': active_session,
        'today_mark': today_mark,
        'todays_appts': todays_appts,
        'todays_appts_count': todays_appts.count(),

        'month_duration_display': _fmt_duration(month_duration),
        'month_days_checked_in': month_days_checked_in,
        'month_expected_days': expected,
        'attendance_pct': attendance_pct,
        'month_completed_sessions': month_completed_sessions,

        'hours_trend': hours_trend,
        'upcoming': upcoming,
        'upcoming_marks': upcoming_marks,
        'month_label': month_start.strftime('%B %Y'),
    }


# ---------------------------------------------------------------------------
# Client dashboard
# ---------------------------------------------------------------------------

def _client_context(user, today, month_start):
    try:
        client = user.client_profile
    except Exception:
        client = Client.active_objects.filter(mobile_number=user.mobile_number).first()

    if not client:
        return {'client_profile': None}

    next_appt = (
        Appointment.active_objects.filter(
            client=client, status=Appointment.Status.SCHEDULED, date__gte=today,
        )
        .select_related('staff', 'therapy_type')
        .order_by('date', 'start_time')
        .first()
    )
    upcoming = (
        Appointment.active_objects.filter(
            client=client, status=Appointment.Status.SCHEDULED, date__gte=today,
        )
        .select_related('staff', 'therapy_type')
        .order_by('date', 'start_time')[:5]
    )

    total_sessions = Appointment.active_objects.filter(
        client=client, status=Appointment.Status.COMPLETED,
    ).count()
    month_sessions = Appointment.active_objects.filter(
        client=client, status=Appointment.Status.COMPLETED,
        date__gte=month_start, date__lte=today,
    ).count()

    total_paid = MonthlyBill.active_objects.filter(
        client=client,
    ).aggregate(total=Sum('paid_amount'))['total'] or 0

    client_agg = MonthlyBill.active_objects.filter(client=client).aggregate(
        billed=Sum('package_amount'), carry=Sum('carry_forward'),
    )
    outstanding_raw = ((client_agg['billed'] or 0)
                       + (client_agg['carry'] or 0)
                       - (total_paid or 0))
    outstanding = outstanding_raw if outstanding_raw > 0 else 0

    overdue_count = MonthlyBill.active_objects.filter(
        client=client,
        status__in=[MonthlyBill.Status.UNPAID, MonthlyBill.Status.PARTIAL],
    ).count()

    recent_sessions = (
        Appointment.active_objects.filter(
            client=client,
            status__in=[Appointment.Status.COMPLETED, Appointment.Status.CANCELLED],
        )
        .select_related('staff', 'therapy_type')
        .order_by('-date', '-start_time')[:5]
    )

    return {
        'client_profile': client,
        'next_appt': next_appt,
        'upcoming': upcoming,
        'total_sessions': total_sessions,
        'month_sessions': month_sessions,
        'total_paid': total_paid,
        'outstanding': outstanding,
        'overdue_count': overdue_count,
        'recent_sessions': recent_sessions,
        'month_label': month_start.strftime('%B %Y'),
    }
