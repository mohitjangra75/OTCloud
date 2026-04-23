import datetime
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from attendance.services import AttendanceError, AttendanceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _staff_required(view_func):
    """Allow only users with role staff or admin."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('staff', 'admin'):
            messages.error(request, "You do not have permission to access attendance.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _admin_required(view_func):
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_superuser or request.user.role == 'admin'):
            messages.error(request, "Admin access required.")
            return redirect('attendance:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def _parse_date(raw, fallback):
    if not raw:
        return fallback
    try:
        return datetime.datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return fallback


def _format_duration(td):
    """Format a timedelta as HH:MM:SS."""
    if td is None:
        return '00:00:00'
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(abs(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _build_personal_context(user):
    """Rich context for the personal dashboard: day-start, day-end, sessions, status."""
    today = timezone.now().date()
    status_info = AttendanceService.get_current_status(user)
    logs = list(AttendanceService.get_daily_logs(user, today).order_by('check_in_time'))
    daily_total = AttendanceService.get_daily_hours(user, today)

    # Future marks by this user for upcoming days (to display below the form)
    from attendance.models import AttendanceMark
    upcoming_marks = list(
        AttendanceMark.active_objects
        .filter(user=user, date__gte=today)
        .order_by('date')
    )

    # Date options for the self-serve mark modal (today + next 7 days)
    date_options = []
    for i in range(AttendanceService.MARK_MAX_DAYS_AHEAD + 1):
        d = today + timedelta(days=i)
        if i == 0:
            label = f"Today · {d:%a %d %b}"
        elif i == 1:
            label = f"Tomorrow · {d:%a %d %b}"
        else:
            label = f"{d:%a %d %b}"
        date_options.append({'iso': d.isoformat(), 'label': label})

    # Day start = earliest check-in, Day end = latest check-out (None if still active)
    day_start = logs[0].check_in_time if logs else None
    day_end = None
    for lg in reversed(logs):
        if lg.check_out_time:
            day_end = lg.check_out_time
            break

    checked_in = status_info['checked_in']
    # Journey state: 'not_started' | 'active' | 'on_break' | 'finished'
    if not logs:
        journey = 'not_started'
    elif checked_in:
        journey = 'active'
    else:
        journey = 'on_break'

    # Status derived from total hours (used for today's present/half-day badge)
    is_future = False
    day_status = AttendanceService._status_for_total(
        daily_total, has_logs=bool(logs), is_future=is_future,
    )

    return {
        'logs': logs,
        'checked_in': checked_in,
        'current_session': status_info['current_session'],
        'daily_total': daily_total,
        'daily_total_display': _format_duration(daily_total),
        'day_start': day_start,
        'day_end': day_end,
        'journey': journey,
        'day_status': day_status,
        'sessions_count': len(logs),
        'today': today,
        'today_mark': AttendanceService.get_mark(user, today),
        'upcoming_marks': upcoming_marks,
        'date_options': date_options,
    }


@method_decorator([login_required, _staff_required], name='dispatch')
class AttendanceDashboardView(View):
    """
    Role-based landing:
      - admin → redirect to team day view
      - staff → personal dashboard (check in/out)
    """
    template_name = 'attendance/dashboard.html'

    def get(self, request):
        user = request.user
        if user.is_superuser or user.role == 'admin':
            return redirect('attendance:team_day')
        return render(request, self.template_name, _build_personal_context(user))


@method_decorator([login_required, _staff_required], name='dispatch')
class MyAttendanceView(View):
    """Explicit personal dashboard — used by admins who also want to check in."""
    template_name = 'attendance/dashboard.html'

    def get(self, request):
        return render(request, self.template_name, _build_personal_context(request.user))


# ---------------------------------------------------------------------------
# Check-in / Check-out
# ---------------------------------------------------------------------------

def _safe_next(request, fallback='attendance:dashboard'):
    """Return POST['next'] if it's a same-host relative path; else the fallback URL."""
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme

    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return nxt
    return reverse(fallback)


@method_decorator([login_required, _staff_required], name='dispatch')
class CheckInView(View):
    http_method_names = ['post']

    def post(self, request):
        try:
            AttendanceService.check_in(request.user)
            messages.success(request, "Checked in successfully.")
        except AttendanceError as exc:
            messages.error(request, str(exc))
        return redirect(_safe_next(request))


@method_decorator([login_required, _staff_required], name='dispatch')
class CheckOutView(View):
    http_method_names = ['post']

    def post(self, request):
        try:
            AttendanceService.check_out(request.user)
            messages.success(request, "Checked out successfully.")
        except AttendanceError as exc:
            messages.error(request, str(exc))
        return redirect(_safe_next(request))


# ---------------------------------------------------------------------------
# History (monthly view)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _staff_required], name='dispatch')
class AttendanceHistoryView(View):
    template_name = 'attendance/history.html'

    def get(self, request):
        user = request.user
        today = timezone.now().date()

        # Allow navigation via ?year=2026&month=3
        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month

        # Clamp values
        month = max(1, min(12, month))

        from attendance.models import AttendanceLog
        logs = AttendanceLog.active_objects.filter(
            user=user,
            date__year=year,
            date__month=month,
        ).order_by('-date', '-check_in_time')

        monthly_total = AttendanceService.get_monthly_hours(user, year, month)

        # Build daily summary
        from collections import OrderedDict
        daily_map = OrderedDict()
        for log in logs:
            day = log.date
            if day not in daily_map:
                daily_map[day] = {
                    'date': day,
                    'logs': [],
                    'total': timedelta(),
                }
            daily_map[day]['logs'].append(log)
            if log.duration:
                daily_map[day]['total'] += log.duration

        for day_info in daily_map.values():
            day_info['total_display'] = _format_duration(day_info['total'])

        # Previous / next month for pagination
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        context = {
            'year': year,
            'month': month,
            'month_name': datetime.date(year, month, 1).strftime('%B'),
            'days': list(daily_map.values()),
            'monthly_total': monthly_total,
            'monthly_total_display': _format_duration(monthly_total),
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Team views (admin): day-wise + month-wise
# ---------------------------------------------------------------------------

@method_decorator([login_required, _staff_required, _admin_required], name='dispatch')
class TeamDayView(View):
    """Day-wise attendance for all active staff. Defaults to today."""
    template_name = 'attendance/team_day.html'

    def get(self, request):
        today = timezone.now().date()
        target_date = _parse_date(request.GET.get('date'), today)

        rows = AttendanceService.get_day_attendance(target_date)

        # Derive summary counts for the header strip
        # A marked-ahead row has status='half_day' / 'absent' even if the date is in the future,
        # so count those first and only fall back to the derived 'upcoming' bucket for unmarked rows.
        present = sum(1 for r in rows if r['status'] == 'present')
        half = sum(1 for r in rows if r['status'] in ('half-day', 'half_day', 'short'))
        absent = sum(1 for r in rows if r['status'] == 'absent')
        upcoming = sum(1 for r in rows if r['status'] == 'upcoming')
        active_now = sum(1 for r in rows if r.get('is_active'))

        # Attach display strings
        for r in rows:
            r['total_display'] = _format_duration(r['total'])

        # Date options for the mark modal: today + next 7 days, with pretty labels
        date_options = []
        for i in range(AttendanceService.MARK_MAX_DAYS_AHEAD + 1):
            d = today + timedelta(days=i)
            if i == 0:
                label = f"Today · {d:%a %d %b}"
            elif i == 1:
                label = f"Tomorrow · {d:%a %d %b}"
            else:
                label = f"{d:%a %d %b}"
            date_options.append({'iso': d.isoformat(), 'label': label, 'selected': d == target_date})

        context = {
            'target_date': target_date,
            'is_today': target_date == today,
            'prev_date': target_date - timedelta(days=1),
            'next_date': target_date + timedelta(days=1),
            'today': today,
            'rows': rows,
            'present_count': present,
            'half_count': half,
            'absent_count': absent,
            'upcoming_count': upcoming,
            'active_now': active_now,
            'total_staff': len(rows),
            'year': target_date.year,
            'month': target_date.month,
            'date_options': date_options,
        }
        return render(request, self.template_name, context)


@method_decorator([login_required, _staff_required, _admin_required], name='dispatch')
class TeamMonthView(View):
    """Month-wise aggregated stats per staff."""
    template_name = 'attendance/team_month.html'

    def get(self, request):
        today = timezone.now().date()
        try:
            year = int(request.GET.get('year', today.year))
            month = int(request.GET.get('month', today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month
        month = max(1, min(12, month))

        rows = AttendanceService.get_month_stats(year, month)

        # Attach display strings + per-row attendance %
        team_total = timedelta()
        team_present = 0
        team_absent = 0
        for r in rows:
            r['total_display'] = _format_duration(r['total'])
            r['avg_display'] = _format_duration(r['avg_per_day'])
            r['attendance_pct'] = (
                round((r['days_present'] / r['expected_days']) * 100)
                if r['expected_days'] else 0
            )
            team_total += r['total']
            team_present += r['days_present']
            team_absent += r['days_absent']

        # Team-wide attendance rate: present / (staff * workdays)
        expected_days = rows[0]['expected_days'] if rows else 0
        total_possible_slots = len(rows) * expected_days
        team_attendance_pct = (
            round((team_present / total_possible_slots) * 100)
            if total_possible_slots else 0
        )

        # Leaderboard: top 3 by attendance % (ties broken by total hours)
        top_performers = sorted(
            rows,
            key=lambda r: (r['attendance_pct'], r['total']),
            reverse=True,
        )[:3] if rows else []

        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

        context = {
            'year': year,
            'month': month,
            'month_name': datetime.date(year, month, 1).strftime('%B'),
            'rows': rows,
            'team_total_display': _format_duration(team_total),
            'team_present': team_present,
            'team_absent': team_absent,
            'team_attendance_pct': team_attendance_pct,
            'expected_days': expected_days,
            'top_performers': top_performers,
            'prev_year': prev_year,
            'prev_month': prev_month,
            'next_year': next_year,
            'next_month': next_month,
            'is_current_month': year == today.year and month == today.month,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Mark / unmark attendance (admin, up to +7 days)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _staff_required], name='dispatch')
class AttendanceMarkView(View):
    """
    Self-serve: employees mark their own half-day / leave for today + next 7 days.

    POST body:
      status ('half_day' | 'leave'),
      dates (comma-separated 'YYYY-MM-DD' values), notes
    """
    http_method_names = ['post']

    def post(self, request):
        from attendance.models import AttendanceMark

        status = (request.POST.get('status') or '').strip()
        dates_raw = request.POST.get('dates', '').strip()
        notes = request.POST.get('notes', '').strip()

        if status not in AttendanceMark.Status.values:
            messages.error(request, "Invalid status.")
            return redirect(_safe_next(request, fallback='attendance:my_attendance'))

        parsed_dates = []
        for raw in [d.strip() for d in dates_raw.split(',') if d.strip()]:
            d = _parse_date(raw, None)
            if d:
                parsed_dates.append(d)

        if not parsed_dates:
            messages.error(request, "Please select at least one date.")
            return redirect(_safe_next(request, fallback='attendance:my_attendance'))

        ok = 0
        errors = []
        for d in parsed_dates:
            try:
                AttendanceService.mark(
                    user=request.user, date=d, status=status,
                    marked_by=request.user, notes=notes,
                )
                ok += 1
            except AttendanceError as exc:
                errors.append(f"{d:%d %b}: {exc}")

        if ok:
            label = dict(AttendanceMark.Status.choices).get(status, status)
            messages.success(
                request,
                f"Marked {label} for {ok} day{'s' if ok > 1 else ''}.",
            )
        for err in errors:
            messages.warning(request, err)

        return redirect(_safe_next(request, fallback='attendance:my_attendance'))


@method_decorator([login_required, _staff_required], name='dispatch')
class AttendanceUnmarkView(View):
    """Self-serve: clear one's own mark for a specific date."""
    http_method_names = ['post']

    def post(self, request):
        date = _parse_date(request.POST.get('date'), None)
        if not date:
            messages.error(request, "Missing date.")
            return redirect(_safe_next(request, fallback='attendance:my_attendance'))

        AttendanceService.unmark(request.user, date)
        messages.success(request, f"Cleared mark for {date:%d %b %Y}.")
        return redirect(_safe_next(request, fallback='attendance:my_attendance'))


# ---------------------------------------------------------------------------
# API – live timer
# ---------------------------------------------------------------------------

@login_required
def live_timer_api(request):
    """
    Return JSON with the current session's elapsed seconds for a JS timer.

    Response:
        { "checked_in": true, "elapsed_seconds": 1234 }
    or
        { "checked_in": false, "elapsed_seconds": 0 }
    """
    if request.user.role not in ('staff', 'admin'):
        return JsonResponse({'error': 'forbidden'}, status=403)

    status = AttendanceService.get_current_status(request.user)

    if status['checked_in']:
        elapsed = timezone.now() - status['current_session'].check_in_time
        elapsed_seconds = int(elapsed.total_seconds())
    else:
        elapsed_seconds = 0

    return JsonResponse({
        'checked_in': status['checked_in'],
        'elapsed_seconds': elapsed_seconds,
    })
