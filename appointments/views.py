import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import User
from appointments.forms import AppointmentForm, RescheduleForm, ReassignStaffForm
from appointments.models import Appointment, TherapyType
from appointments.services import AppointmentService, AppointmentServiceError
from clients.models import Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_or_staff_required(view_func):
    """Allow admin or staff (read-only pages like list + schedule grid)."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ('admin', 'staff')):
            messages.error(request, "You do not have permission to perform this action.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _admin_required(view_func):
    """Admin-only actions: create/edit/delete/cancel/reschedule/reassign/complete/mark-absent."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role == 'admin'):
            messages.error(request, "Only admins can perform this action.")
            return redirect('appointments:appointment_list')
        return view_func(request, *args, **kwargs)
    return wrapper


def _admin_or_client_required(view_func):
    """Admin (anyone) OR client (their own — checked inside the view). Blocks staff."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.role == 'staff':
            messages.error(request, "Only admins can change appointments. Please contact your admin.")
            pk = kwargs.get('pk')
            if pk:
                return redirect('appointments:appointment_detail', pk=pk)
            return redirect('appointments:appointment_list')
        if not user.is_authenticated:
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_client_for_user(user):
    """Find the Client record for a user - by linked user FK or by mobile number."""
    try:
        return user.client_profile
    except Client.DoesNotExist:
        pass
    return Client.active_objects.filter(mobile_number=user.mobile_number).first()


def _get_appointments_for_user(user):
    """Return the appropriate queryset based on user role."""
    if user.is_superuser or user.role == 'admin':
        return AppointmentService.get_all_appointments()
    elif user.role == 'staff':
        return AppointmentService.get_staff_appointments(user)
    else:
        client = _get_client_for_user(user)
        if client:
            return AppointmentService.get_client_appointments(client)
        return Appointment.active_objects.none()


def _check_client_owns_appointment(user, appointment):
    """Return True if user is client and owns this appointment."""
    if user.role == 'client':
        client = _get_client_for_user(user)
        return client and appointment.client == client
    return False


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@method_decorator([login_required], name='dispatch')
class AppointmentListView(View):
    template_name = 'appointments/appointment_list.html'
    paginate_by = 20

    def get(self, request):
        appointments = _get_appointments_for_user(request.user).select_related(
            'client', 'staff', 'therapy_type'
        )

        status_filter = request.GET.get('status', '').strip()
        valid_statuses = [choice[0] for choice in Appointment.Status.choices]
        if status_filter and status_filter in valid_statuses:
            appointments = appointments.filter(status=status_filter)
        elif status_filter:
            status_filter = ''

        paginator = Paginator(appointments, self.paginate_by)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'page_obj': page_obj,
            'appointments': page_obj,
            'status_choices': Appointment.Status.choices,
            'current_status': status_filter,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@method_decorator([login_required], name='dispatch')
class AppointmentDetailView(View):
    template_name = 'appointments/appointment_detail.html'

    def get(self, request, pk):
        appointment = get_object_or_404(
            Appointment.active_objects.select_related('client', 'staff', 'therapy_type'), pk=pk
        )

        user = request.user
        if user.role == 'client':
            client = _get_client_for_user(user)
            if not client or appointment.client != client:
                messages.error(request, "You do not have permission to view this appointment.")
                return redirect('appointments:appointment_list')

        session_count = AppointmentService.get_client_sessions_count(appointment.client_id)
        is_active = appointment.status in (
            Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED
        )

        context = {
            'appointment': appointment,
            'session_count': session_count,
            'is_active': is_active,
            'is_client': user.role == 'client',
            'is_staff': user.role == 'staff',
            'is_admin': user.is_superuser or user.role == 'admin',
            'is_staff_or_admin': user.role in ('staff', 'admin') or user.is_superuser,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class AppointmentCreateView(View):
    template_name = 'appointments/appointment_form.html'

    def _initial_from_query(self, request):
        """Pre-fill from ?lead_id=&client_name=&client_mobile= query string."""
        initial = {}
        for k in ('client_name', 'client_mobile'):
            v = request.GET.get(k)
            if v:
                initial[k] = v
        return initial

    def get(self, request):
        form = AppointmentForm(initial=self._initial_from_query(request))
        return render(request, self.template_name, {
            'form': form, 'action': 'Create',
            'lead_id': request.GET.get('lead_id') or '',
        })

    def post(self, request):
        form = AppointmentForm(request.POST)
        warnings = []
        if form.is_valid():
            cd = form.cleaned_data
            # Conflict detection — surface warnings; admin can re-submit with confirm=1 to bypass
            conflicts = AppointmentService.detect_conflicts(
                staff=cd['staff'],
                date_=cd['date'],
                start_time=cd['start_time'],
                end_time=cd['end_time'],
            )
            confirmed = request.POST.get('confirm') == '1'
            if conflicts and not confirmed:
                if 'on_leave' in conflicts:
                    warnings.append(
                        f"⚠ {cd['staff'].get_full_name() or cd['staff'].mobile_number} "
                        f"is on LEAVE on {cd['date']:%d %b}. The appointment will be flagged for reassignment."
                    )
                if 'half_day' in conflicts:
                    warnings.append(
                        f"ℹ {cd['staff'].get_full_name() or cd['staff'].mobile_number} "
                        f"is on a HALF-DAY on {cd['date']:%d %b}."
                    )
                if 'overlap' in conflicts:
                    parts = ', '.join(
                        f"{a.start_time.strftime('%I:%M %p')} {a.display_name}"
                        for a in conflicts['overlap']
                    )
                    warnings.append(
                        f"⚠ Time conflict: {cd['staff'].get_full_name() or cd['staff'].mobile_number} "
                        f"already has — {parts}."
                    )
                return render(request, self.template_name, {
                    'form': form, 'action': 'Create',
                    'warnings': warnings,
                    'confirmation_required': True,
                    'lead_id': request.POST.get('lead_id') or '',
                })

            appointment = form.save(commit=False)
            appointment.created_by = request.user
            appointment.save()

            # If we came from a Lead, mark it as CONVERTED
            lead_id = (request.POST.get('lead_id') or '').strip()
            if lead_id:
                try:
                    from lms.models import Lead
                    lead = Lead.active_objects.filter(pk=lead_id).first()
                    if lead and lead.status != Lead.Status.CONVERTED:
                        lead.status = Lead.Status.CONVERTED
                        lead.save(update_fields=['status', 'updated_at'])
                except Exception:
                    pass

            messages.success(request, "Appointment created and added to the schedule.")
            return redirect(f"/schedule/?date={appointment.date.isoformat()}")
        return render(request, self.template_name, {
            'form': form, 'action': 'Create',
            'lead_id': request.POST.get('lead_id') or '',
        })


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentUpdateView(View):
    template_name = 'appointments/appointment_form.html'

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = AppointmentForm(instance=appointment)
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
            'action': 'Update',
        })

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.updated_by = request.user
            appointment.save()
            messages.success(request, "Appointment updated successfully.")
            return redirect('appointments:appointment_detail', pk=appointment.pk)
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
            'action': 'Update',
        })


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentDeleteView(View):
    template_name = 'appointments/appointment_confirm_delete.html'

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        return render(request, self.template_name, {'appointment': appointment})

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        appointment.updated_by = request.user
        appointment.soft_delete()
        messages.success(request, "Appointment deleted successfully.")
        return redirect('appointments:appointment_list')


# ---------------------------------------------------------------------------
# Reschedule (both client and staff)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_client_required], name='dispatch')
class AppointmentRescheduleView(View):
    template_name = 'appointments/reschedule.html'

    def _check_permission(self, request, appointment):
        user = request.user
        if user.role == 'client':
            if not _check_client_owns_appointment(user, appointment):
                messages.error(request, "You do not have permission to reschedule this appointment.")
                return redirect('appointments:appointment_list')
        return None

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        denied = self._check_permission(request, appointment)
        if denied:
            return denied
        form = RescheduleForm(initial={
            'new_date': appointment.date,
            'new_start_time': appointment.start_time,
            'new_end_time': appointment.end_time,
        })
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
        })

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        denied = self._check_permission(request, appointment)
        if denied:
            return denied
        form = RescheduleForm(request.POST)
        if form.is_valid():
            try:
                new_appointment = AppointmentService.reschedule(
                    appointment_id=pk,
                    new_date=form.cleaned_data['new_date'],
                    new_start_time=form.cleaned_data['new_start_time'],
                    new_end_time=form.cleaned_data['new_end_time'],
                    updated_by=request.user,
                )
                messages.success(request, "Appointment rescheduled successfully.")
                return redirect('appointments:appointment_detail', pk=new_appointment.pk)
            except AppointmentServiceError as exc:
                messages.error(request, str(exc))
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
        })


# ---------------------------------------------------------------------------
# Cancel (both client and staff)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_client_required], name='dispatch')
class AppointmentCancelView(View):
    template_name = 'appointments/appointment_cancel.html'

    def _check_permission(self, request, appointment):
        user = request.user
        if user.role == 'client':
            if not _check_client_owns_appointment(user, appointment):
                messages.error(request, "You do not have permission to cancel this appointment.")
                return redirect('appointments:appointment_list')
        return None

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        denied = self._check_permission(request, appointment)
        if denied:
            return denied
        return render(request, self.template_name, {'appointment': appointment})

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        denied = self._check_permission(request, appointment)
        if denied:
            return denied

        reason = request.POST.get('reason', '').strip()
        try:
            AppointmentService.cancel(
                appointment_id=pk,
                reason=reason,
                cancelled_by=request.user,
            )
            messages.success(request, "Appointment cancelled successfully.")
        except AppointmentServiceError as exc:
            messages.error(request, str(exc))
        return redirect('appointments:appointment_list')


# ---------------------------------------------------------------------------
# Complete (staff/admin only)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentCompleteView(View):
    http_method_names = ['post']

    def post(self, request, pk):
        try:
            AppointmentService.complete_appointment(pk, completed_by=request.user)
            messages.success(request, "Appointment marked as completed.")
        except AppointmentServiceError as exc:
            messages.error(request, str(exc))
        return redirect('appointments:appointment_detail', pk=pk)


# ---------------------------------------------------------------------------
# Reassign Staff (staff/admin only)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Daily Schedule (grid view)
# ---------------------------------------------------------------------------

def _parse_date(raw, fallback):
    if not raw:
        return fallback
    try:
        return datetime.datetime.strptime(raw, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return fallback


def _safe_next_url(request, fallback):
    """Return POST['next'] if same-host, else fallback URL."""
    from django.utils.http import url_has_allowed_host_and_scheme
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        url=nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return nxt
    return fallback


@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class EmployeeScheduleView(View):
    """Per-employee weekly schedule: time-slot rows × day columns."""
    template_name = 'appointments/employee_schedule.html'

    def get(self, request):
        today = timezone.localdate()

        all_staff = list(
            User.objects.filter(
                role__in=['staff', 'admin'], is_active=True,
            ).order_by('first_name', 'last_name')
        )
        if not all_staff:
            messages.error(request, "No active staff found.")
            return redirect('daily_schedule')

        # Selected staff: from query → else self if staff role → else first
        staff_id = request.GET.get('staff_id')
        selected_staff = None
        if staff_id:
            selected_staff = next((s for s in all_staff if str(s.pk) == str(staff_id)), None)
        if not selected_staff:
            selected_staff = (
                next((s for s in all_staff if s.pk == request.user.pk), None)
                or all_staff[0]
            )

        # Week starting Monday
        default_start = today - datetime.timedelta(days=today.weekday())
        week_start = _parse_date(request.GET.get('start'), default_start)

        data = AppointmentService.get_employee_week_schedule(selected_staff, week_start, days=7)

        # Build rows for the template
        rows = []
        for slot_time, label in data['slots']:
            cells = [data['grid'].get((d, slot_time)) for d in data['week_dates']]
            rows.append({'time': slot_time, 'label': label, 'cells': cells})

        # Day headers with hints
        from attendance.models import AttendanceMark
        marks_by_date = {
            m.date: m for m in AttendanceMark.active_objects.filter(
                user=selected_staff,
                date__gte=data['week_dates'][0],
                date__lte=data['week_dates'][-1],
            )
        }
        days = []
        for d in data['week_dates']:
            mark = marks_by_date.get(d)
            days.append({
                'date': d,
                'iso': d.isoformat(),
                'is_today': d == today,
                'is_past': d < today,
                'is_weekend': d.weekday() == 6,  # Sunday off
                'mark': mark,
            })

        total_hours = data['total_minutes'] // 60
        total_min_remainder = data['total_minutes'] % 60

        context = {
            'all_staff': all_staff,
            'selected_staff': selected_staff,
            'week_start': week_start,
            'week_end': data['week_dates'][-1],
            'days': days,
            'rows': rows,
            'today': today,
            'prev_week': week_start - datetime.timedelta(days=7),
            'next_week': week_start + datetime.timedelta(days=7),
            'this_week_start': default_start,
            'total_appointments': data['total_appointments'],
            'total_hours': total_hours,
            'total_min_remainder': total_min_remainder,
            'pending_count': data['pending_reassignments'],
            'clients': Client.active_objects.all().order_by('first_name', 'last_name'),
            'therapy_types': TherapyType.active_objects.all(),
        }
        return render(request, self.template_name, context)


@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class DailyScheduleView(View):
    """Day-wise grid: staff columns x time-slot rows. Defaults to tomorrow."""
    template_name = 'appointments/daily_schedule.html'

    def get(self, request):
        today = timezone.localdate()
        tomorrow = today + datetime.timedelta(days=1)
        target_date = _parse_date(request.GET.get('date'), today)

        data = AppointmentService.get_day_schedule(target_date)

        # Build rows for the template: list of { 'time', 'label', 'cells': [appt_or_None] }
        rows = []
        for slot_time, label in data['slots']:
            cells = [data['grid'].get((s.id, slot_time)) for s in data['staff']]
            rows.append({'time': slot_time, 'label': label, 'cells': cells})

        pending_reassignments = AppointmentService.get_pending_reassignments(target_date)

        # Staff who are on leave on the target date → exclude from reassign dropdown.
        from attendance.models import AttendanceMark
        on_leave_ids = set(
            AttendanceMark.active_objects.filter(
                date=target_date,
                status=AttendanceMark.Status.LEAVE,
            ).values_list('user_id', flat=True)
        )
        available_staff = [s for s in data['staff'] if s.id not in on_leave_ids]

        context = {
            'target_date': target_date,
            'is_today': target_date == today,
            'is_tomorrow': target_date == tomorrow,
            'prev_date': target_date - datetime.timedelta(days=1),
            'next_date': target_date + datetime.timedelta(days=1),
            'today': today,
            'tomorrow': tomorrow,
            'staff': data['staff'],
            'available_staff': available_staff,
            'on_leave_ids': on_leave_ids,
            'rows': rows,
            'clients': Client.active_objects.all().order_by('first_name', 'last_name'),
            'therapy_types': TherapyType.active_objects.all(),
            'pending_reassignments': pending_reassignments,
        }
        return render(request, self.template_name, context)


@method_decorator([login_required, _admin_required], name='dispatch')
class ScheduleQuickAddView(View):
    http_method_names = ['post']

    def post(self, request):
        target_date = _parse_date(request.POST.get('date'), timezone.localdate())
        fallback = f"{reverse('daily_schedule')}?date={target_date}"

        raw_time = request.POST.get('start_time', '').strip()
        try:
            start_time = datetime.datetime.strptime(raw_time, '%H:%M:%S').time()
        except ValueError:
            try:
                start_time = datetime.datetime.strptime(raw_time, '%H:%M').time()
            except ValueError:
                messages.error(request, "Invalid time.")
                return redirect(_safe_next_url(request, fallback))

        staff_id = request.POST.get('staff_id')
        client_id = request.POST.get('client_id')
        therapy_id = request.POST.get('therapy_type_id')
        is_group = request.POST.get('is_group') == 'on'

        staff = User.objects.filter(pk=staff_id, is_active=True).first()
        client = Client.active_objects.filter(pk=client_id).first()
        therapy_type = TherapyType.active_objects.filter(pk=therapy_id).first()

        if not (staff and client and therapy_type):
            messages.error(request, "Staff, client and therapy type are required.")
            return redirect(_safe_next_url(request, fallback))

        try:
            AppointmentService.quick_create(
                client=client,
                staff=staff,
                therapy_type=therapy_type,
                date=target_date,
                start_time=start_time,
                created_by=request.user,
                is_group=is_group,
                notes=request.POST.get('notes', ''),
            )
            messages.success(request, "Appointment added.")
        except AppointmentServiceError as exc:
            messages.error(request, str(exc))

        return redirect(_safe_next_url(request, fallback))


@method_decorator([login_required, _admin_required], name='dispatch')
class ScheduleCopyDayView(View):
    http_method_names = ['post']

    def post(self, request):
        target_date = _parse_date(request.POST.get('target_date'), None)
        source_date = _parse_date(
            request.POST.get('source_date'),
            (target_date - datetime.timedelta(days=1)) if target_date else None,
        )
        if not (target_date and source_date):
            messages.error(request, "Invalid dates for copy.")
            return redirect('daily_schedule')

        try:
            count = AppointmentService.copy_day(source_date, target_date, created_by=request.user)
            if count:
                messages.success(request, f"Copied {count} appointments from {source_date:%d %b} to {target_date:%d %b}.")
            else:
                messages.info(request, "Nothing new to copy — target day already has those slots.")
        except Exception as exc:
            messages.error(request, f"Could not copy schedule: {exc}")

        return redirect(f"{reverse('daily_schedule')}?date={target_date}")


@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentMarkAbsentView(View):
    http_method_names = ['post']

    def post(self, request, pk):
        try:
            appt = AppointmentService.mark_absent(pk, updated_by=request.user)
            messages.success(request, f"{appt.client.full_name} marked absent.")
        except AppointmentServiceError as exc:
            messages.error(request, str(exc))
        redirect_date = request.POST.get('date') or timezone.localdate().isoformat()
        return redirect(f"{reverse('daily_schedule')}?date={redirect_date}")


@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentQuickReassignView(View):
    """Inline reassign used by the pending-reassignment banner on the schedule."""
    http_method_names = ['post']

    def post(self, request, pk):
        new_staff_id = request.POST.get('new_staff_id')
        new_staff = User.objects.filter(
            pk=new_staff_id, is_active=True, role__in=['staff', 'admin'],
        ).first()
        if not new_staff:
            messages.error(request, "Pick a valid staff member.")
            return redirect(request.META.get('HTTP_REFERER') or reverse('daily_schedule'))

        try:
            AppointmentService.reassign_staff(
                appointment_id=pk,
                new_staff=new_staff,
                reassigned_by=request.user,
            )
            messages.success(request, "Reassigned.")
        except AppointmentServiceError as exc:
            messages.error(request, str(exc))

        return redirect(request.META.get('HTTP_REFERER') or reverse('daily_schedule'))


@method_decorator([login_required, _admin_required], name='dispatch')
class AppointmentReassignView(View):
    template_name = 'appointments/reassign.html'

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = ReassignStaffForm(
            initial={'new_staff': appointment.staff},
            exclude_date=appointment.date,
        )
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
        })

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = ReassignStaffForm(request.POST, exclude_date=appointment.date)
        if form.is_valid():
            try:
                AppointmentService.reassign_staff(
                    appointment_id=pk,
                    new_staff=form.cleaned_data['new_staff'],
                    reassigned_by=request.user,
                )
                messages.success(request, "Appointment reassigned successfully.")
                return redirect('appointments:appointment_detail', pk=pk)
            except AppointmentServiceError as exc:
                messages.error(request, str(exc))
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
        })
