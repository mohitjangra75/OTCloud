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
    """Allow only staff / superuser users."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "You do not have permission to access attendance.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


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

@method_decorator([login_required, _staff_required], name='dispatch')
class AttendanceDashboardView(View):
    template_name = 'attendance/dashboard.html'

    def get(self, request):
        user = request.user
        today = timezone.now().date()

        status = AttendanceService.get_current_status(user)
        logs = AttendanceService.get_daily_logs(user, today)
        daily_total = AttendanceService.get_daily_hours(user, today)

        context = {
            'logs': logs,
            'checked_in': status['checked_in'],
            'current_session': status['current_session'],
            'daily_total': daily_total,
            'daily_total_display': _format_duration(daily_total),
            'today': today,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Check-in / Check-out
# ---------------------------------------------------------------------------

@method_decorator([login_required, _staff_required], name='dispatch')
class CheckInView(View):
    http_method_names = ['post']

    def post(self, request):
        try:
            AttendanceService.check_in(request.user)
            messages.success(request, "Checked in successfully.")
        except AttendanceError as exc:
            messages.error(request, str(exc))
        return redirect('attendance:dashboard')


@method_decorator([login_required, _staff_required], name='dispatch')
class CheckOutView(View):
    http_method_names = ['post']

    def post(self, request):
        try:
            AttendanceService.check_out(request.user)
            messages.success(request, "Checked out successfully.")
        except AttendanceError as exc:
            messages.error(request, str(exc))
        return redirect('attendance:dashboard')


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
    if not (request.user.is_staff or request.user.is_superuser):
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
