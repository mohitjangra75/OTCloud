from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from appointments.forms import AppointmentForm, RescheduleForm, ReassignStaffForm
from appointments.models import Appointment
from appointments.services import AppointmentService, AppointmentServiceError
from clients.models import Client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_or_staff_required(view_func):
    """Allow only admin or staff role users."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ('admin', 'staff')):
            messages.error(request, "You do not have permission to perform this action.")
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
            'is_staff_or_admin': user.role in ('staff', 'admin') or user.is_superuser,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class AppointmentCreateView(View):
    template_name = 'appointments/appointment_form.html'

    def get(self, request):
        form = AppointmentForm()
        return render(request, self.template_name, {'form': form, 'action': 'Create'})

    def post(self, request):
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.created_by = request.user
            appointment.save()
            messages.success(request, "Appointment created successfully.")
            return redirect('appointments:appointment_detail', pk=appointment.pk)
        return render(request, self.template_name, {'form': form, 'action': 'Create'})


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
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

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
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

@method_decorator([login_required], name='dispatch')
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

@method_decorator([login_required], name='dispatch')
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

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
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

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class AppointmentReassignView(View):
    template_name = 'appointments/reassign.html'

    def get(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = ReassignStaffForm(initial={'new_staff': appointment.staff})
        return render(request, self.template_name, {
            'form': form,
            'appointment': appointment,
        })

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.active_objects, pk=pk)
        form = ReassignStaffForm(request.POST)
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
