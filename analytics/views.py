from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Sum, Count, Q, Subquery, OuterRef
from datetime import timedelta

from accounts.models import User
from attendance.models import AttendanceLog
from appointments.models import Appointment
from clients.models import Client
from billing.models import Invoice
from lms.models import Lead, FollowUp


@login_required
def dashboard_view(request):
    user = request.user
    today = timezone.localdate()
    current_month_start = today.replace(day=1)

    context = {'today': today}

    if user.role in (User.Role.ADMIN, User.Role.STAFF):
        context.update(_get_staff_dashboard(user, today, current_month_start))
    else:
        context.update(_get_client_dashboard(user, today))

    if user.is_admin:
        context.update(_get_admin_overview(today, current_month_start))

    return render(request, 'analytics/dashboard.html', context)


def _get_staff_dashboard(user, today, month_start):
    # Attendance stats
    today_logs = AttendanceLog.active_objects.filter(user=user, date=today)
    today_duration = today_logs.aggregate(total=Sum('duration'))['total'] or timedelta()

    month_logs = AttendanceLog.active_objects.filter(
        user=user, date__gte=month_start, date__lte=today
    )
    month_duration = month_logs.aggregate(total=Sum('duration'))['total'] or timedelta()

    # Appointment stats
    upcoming_appointments = Appointment.active_objects.filter(
        staff=user, date__gte=today, status=Appointment.Status.SCHEDULED
    ).count()

    completed_sessions = Appointment.active_objects.filter(
        staff=user, status=Appointment.Status.COMPLETED
    ).count()

    month_sessions = Appointment.active_objects.filter(
        staff=user, date__gte=month_start, date__lte=today,
        status=Appointment.Status.COMPLETED
    ).count()

    # Today's schedule
    todays_appointments = Appointment.active_objects.filter(
        staff=user, date=today
    ).select_related('client').order_by('start_time')[:5]

    return {
        'today_hours': _format_duration(today_duration),
        'month_hours': _format_duration(month_duration),
        'upcoming_appointments': upcoming_appointments,
        'completed_sessions': completed_sessions,
        'month_sessions': month_sessions,
        'todays_appointments': todays_appointments,
        'attendance_days': month_logs.values('date').distinct().count(),
    }


def _get_client_dashboard(user, today):
    # Find client by linked user or by mobile number
    try:
        client = user.client_profile
    except Exception:
        client = Client.active_objects.filter(mobile_number=user.mobile_number).first()
    if not client:
        return {'client_profile': None}

    total_sessions = Appointment.active_objects.filter(
        client=client, status=Appointment.Status.COMPLETED
    ).count()

    upcoming = Appointment.active_objects.filter(
        client=client, date__gte=today, status=Appointment.Status.SCHEDULED
    ).select_related('staff').order_by('date', 'start_time')[:5]

    total_paid = Invoice.active_objects.filter(
        client=client, status=Invoice.Status.PAID
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    pending_invoices = Invoice.active_objects.filter(
        client=client, status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE]
    ).count()

    # Recent completed appointments
    recent_appointments = Appointment.active_objects.filter(
        client=client, status=Appointment.Status.COMPLETED
    ).select_related('staff').order_by('-date', '-start_time')[:5]

    return {
        'client_profile': client,
        'total_sessions': total_sessions,
        'upcoming_appointments': upcoming,
        'total_paid': total_paid,
        'pending_invoices': pending_invoices,
        'recent_appointments': recent_appointments,
    }


def _get_admin_overview(today, month_start):
    total_staff = User.objects.filter(role=User.Role.STAFF, is_active=True).count()
    total_clients = Client.active_objects.count()
    total_leads = Lead.active_objects.filter(status__in=['new', 'contacted', 'interested']).count()

    # Revenue this month
    month_revenue = Invoice.active_objects.filter(
        status=Invoice.Status.PAID,
        created_at__date__gte=month_start,
    ).aggregate(total=Sum('paid_amount'))['total'] or 0

    pending_revenue = Invoice.active_objects.filter(
        status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE],
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    # Today's overview
    checked_in_today = AttendanceLog.active_objects.filter(
        date=today, check_out_time__isnull=True
    ).count()

    today_appointments = Appointment.active_objects.filter(date=today).count()

    pending_follow_ups = FollowUp.active_objects.filter(
        follow_up_date__date__lte=today, status='pending'
    ).count()

    # Recent leads
    recent_leads = Lead.active_objects.all()[:5]

    # --- Enhanced admin data ---

    # All staff with annotated stats
    all_staff = User.objects.filter(
        role=User.Role.STAFF, is_active=True
    ).annotate(
        total_sessions=Count(
            'staff_appointments',
            filter=Q(staff_appointments__status=Appointment.Status.COMPLETED,
                     staff_appointments__is_deleted=False),
        ),
        month_sessions=Count(
            'staff_appointments',
            filter=Q(staff_appointments__status=Appointment.Status.COMPLETED,
                     staff_appointments__date__gte=month_start,
                     staff_appointments__date__lte=today,
                     staff_appointments__is_deleted=False),
        ),
        month_attendance_hours=Sum(
            'attendance_logs__duration',
            filter=Q(attendance_logs__date__gte=month_start,
                     attendance_logs__date__lte=today,
                     attendance_logs__is_deleted=False),
        ),
    ).order_by('first_name', 'last_name')

    # All clients with annotated stats
    all_clients = Client.active_objects.annotate(
        total_sessions=Count(
            'appointments',
            filter=Q(appointments__status=Appointment.Status.COMPLETED,
                     appointments__is_deleted=False),
        ),
        total_paid=Sum(
            'invoices__paid_amount',
            filter=Q(invoices__status=Invoice.Status.PAID,
                     invoices__is_deleted=False),
        ),
        upcoming_sessions=Count(
            'appointments',
            filter=Q(appointments__status=Appointment.Status.SCHEDULED,
                     appointments__date__gte=today,
                     appointments__is_deleted=False),
        ),
    ).order_by('first_name', 'last_name')

    # Top 5 employees by completed sessions this month
    top_employees = User.objects.filter(
        role=User.Role.STAFF, is_active=True
    ).annotate(
        month_completed=Count(
            'staff_appointments',
            filter=Q(staff_appointments__status=Appointment.Status.COMPLETED,
                     staff_appointments__date__gte=month_start,
                     staff_appointments__date__lte=today,
                     staff_appointments__is_deleted=False),
        ),
    ).order_by('-month_completed')[:5]

    # All-time revenue
    total_revenue_all_time = Invoice.active_objects.filter(
        status=Invoice.Status.PAID,
    ).aggregate(total=Sum('paid_amount'))['total'] or 0

    # New clients this month
    new_clients_this_month = Client.active_objects.filter(
        created_at__date__gte=month_start,
    ).count()

    # New leads this month
    new_leads_this_month = Lead.active_objects.filter(
        created_at__date__gte=month_start,
    ).count()

    return {
        'total_staff': total_staff,
        'total_clients': total_clients,
        'total_leads': total_leads,
        'month_revenue': month_revenue,
        'pending_revenue': pending_revenue,
        'checked_in_today': checked_in_today,
        'today_appointments_count': today_appointments,
        'pending_follow_ups': pending_follow_ups,
        'recent_leads': recent_leads,
        'all_staff': all_staff,
        'all_clients': all_clients,
        'top_employees': top_employees,
        'total_revenue_all_time': total_revenue_all_time,
        'new_clients_this_month': new_clients_this_month,
        'new_leads_this_month': new_leads_this_month,
    }


def _format_duration(duration):
    if not duration:
        return '0h 0m'
    total_seconds = int(duration.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f'{hours}h {minutes}m'
