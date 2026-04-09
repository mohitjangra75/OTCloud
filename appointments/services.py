import datetime

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment


class AppointmentServiceError(Exception):
    """Raised when an appointment service operation fails."""
    pass


class AppointmentService:
    """Service layer for appointment operations."""

    @staticmethod
    def create_appointment(data, created_by=None):
        """Create and return a new Appointment."""
        appointment = Appointment(**data)
        if created_by:
            appointment.created_by = created_by
        appointment.calculate_price()
        appointment.full_clean()
        appointment.save()
        return appointment

    @staticmethod
    def get_appointment(appointment_id):
        """Return a single appointment or raise AppointmentServiceError."""
        try:
            return Appointment.active_objects.get(pk=appointment_id)
        except Appointment.DoesNotExist:
            raise AppointmentServiceError("Appointment not found.")

    @staticmethod
    def reschedule(appointment_id, new_date, new_start_time, new_end_time=None, updated_by=None):
        """
        Reschedule an appointment. Marks old as RESCHEDULED, creates new SCHEDULED.
        Preserves therapy type and duration. Adds remark noting who initiated.
        """
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be rescheduled."
            )

        actor = _get_actor_label(updated_by)
        remark = f"[Rescheduled by {actor} on {timezone.localtime().strftime('%d %b %Y, %I:%M %p')}]"

        appointment.status = Appointment.Status.RESCHEDULED
        appointment.notes = (appointment.notes + '\n' if appointment.notes else '') + remark
        if updated_by:
            appointment.updated_by = updated_by
        appointment.save()

        # Create the new appointment with same therapy type/duration/price
        new_appointment = Appointment(
            client=appointment.client,
            staff=appointment.staff,
            therapy_type=appointment.therapy_type,
            duration_minutes=appointment.duration_minutes,
            session_price=appointment.session_price,
            date=new_date,
            start_time=new_start_time,
            end_time=new_end_time or appointment.end_time,
            status=Appointment.Status.SCHEDULED,
            notes=f"Rescheduled from {appointment.date.strftime('%d %b %Y')}",
            created_by=updated_by,
        )
        new_appointment.full_clean()
        new_appointment.save()
        return new_appointment

    @staticmethod
    def cancel(appointment_id, reason='', cancelled_by=None):
        """Cancel an appointment with time restriction and audit trail."""
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be cancelled."
            )

        cancel_hours = getattr(settings, 'APPOINTMENT_CANCEL_HOURS', 6)
        appointment_datetime = timezone.make_aware(
            datetime.datetime.combine(appointment.date, appointment.start_time),
            timezone.get_current_timezone(),
        )
        cutoff = appointment_datetime - datetime.timedelta(hours=cancel_hours)

        if timezone.now() > cutoff:
            raise AppointmentServiceError(
                f"Appointments must be cancelled at least {cancel_hours} hours in advance."
            )

        actor = _get_actor_label(cancelled_by)
        cancel_remark = f"Cancelled by {actor} on {timezone.localtime().strftime('%d %b %Y, %I:%M %p')}"
        if reason:
            cancel_remark = f"{reason}\n\n— {cancel_remark}"
        else:
            cancel_remark = f"No reason provided.\n\n— {cancel_remark}"

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = cancel_remark
        if cancelled_by:
            appointment.updated_by = cancelled_by
        appointment.save()
        return appointment

    @staticmethod
    def complete_appointment(appointment_id, completed_by=None):
        """
        Mark an appointment as completed.
        Auto-generates an invoice item for the session.
        """
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be marked as completed."
            )

        appointment.status = Appointment.Status.COMPLETED
        if completed_by:
            appointment.updated_by = completed_by
        appointment.save()

        # Auto-generate invoice if therapy type and price exist
        if appointment.therapy_type and appointment.session_price > 0:
            _auto_invoice_session(appointment, completed_by)

        return appointment

    @staticmethod
    def reassign_staff(appointment_id, new_staff, reassigned_by=None):
        """Reassign an appointment to a different staff member."""
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be reassigned."
            )

        old_staff_name = appointment.staff.get_full_name() or appointment.staff.mobile_number
        new_staff_name = new_staff.get_full_name() or new_staff.mobile_number

        remark = f"[Reassigned from {old_staff_name} to {new_staff_name} on {timezone.localtime().strftime('%d %b %Y, %I:%M %p')}]"
        appointment.staff = new_staff
        appointment.notes = (appointment.notes + '\n' if appointment.notes else '') + remark
        if reassigned_by:
            appointment.updated_by = reassigned_by
        appointment.save()
        return appointment

    @staticmethod
    def get_upcoming(user):
        now = timezone.now()
        today = now.date()
        current_time = now.time()

        base_qs = Appointment.active_objects.filter(
            status=Appointment.Status.SCHEDULED,
        ).filter(
            Q(date__gt=today) | Q(date=today, start_time__gte=current_time)
        )

        if hasattr(user, 'client_profile'):
            return base_qs.filter(client=user.client_profile)
        if user.role == 'staff':
            return base_qs.filter(staff=user)
        return base_qs

    @staticmethod
    def get_client_sessions_count(client_id):
        return Appointment.active_objects.filter(
            client_id=client_id,
            status=Appointment.Status.COMPLETED,
        ).count()

    @staticmethod
    def get_all_appointments():
        return Appointment.active_objects.all()

    @staticmethod
    def get_staff_appointments(staff_user):
        return Appointment.active_objects.filter(staff=staff_user)

    @staticmethod
    def get_client_appointments(client):
        return Appointment.active_objects.filter(client=client)


# ---------------------------------------------------------------------------
# Helpers (module-level, not part of the class)
# ---------------------------------------------------------------------------

def _get_actor_label(user):
    """Return a human-readable label for who performed an action."""
    if not user:
        return "System"
    name = user.get_full_name() or user.mobile_number
    if user.role == 'client':
        return f"Client ({name})"
    return f"Staff ({name})"


def _auto_invoice_session(appointment, created_by=None):
    """Create an invoice item for a completed appointment session."""
    from billing.services import BillingService

    therapy_name = appointment.therapy_type.name
    duration_label = f"{appointment.duration_minutes} min"
    description = f"{therapy_name} ({duration_label}) - {appointment.date.strftime('%d %b %Y')}"

    BillingService.append_daily_session(
        client=appointment.client,
        appointment=appointment,
        description=description,
        amount=appointment.session_price,
        created_by=created_by,
    )
