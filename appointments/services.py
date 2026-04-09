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
        Reschedule an appointment to a new date/time.
        The old status is changed to RESCHEDULED and a new appointment is created.
        """
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be rescheduled."
            )

        # Mark current appointment as rescheduled
        appointment.status = Appointment.Status.RESCHEDULED
        if updated_by:
            appointment.updated_by = updated_by
        appointment.save()

        # Create the new appointment
        new_appointment = Appointment(
            client=appointment.client,
            staff=appointment.staff,
            date=new_date,
            start_time=new_start_time,
            end_time=new_end_time or appointment.end_time,
            status=Appointment.Status.SCHEDULED,
            notes=appointment.notes,
            created_by=updated_by,
        )
        new_appointment.full_clean()
        new_appointment.save()
        return new_appointment

    @staticmethod
    def cancel(appointment_id, reason='', cancelled_by=None):
        """
        Cancel an appointment. Must be at least APPOINTMENT_CANCEL_HOURS
        before the appointment start.
        """
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

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = reason
        if cancelled_by:
            appointment.updated_by = cancelled_by
        appointment.save()
        return appointment

    @staticmethod
    def complete_appointment(appointment_id, completed_by=None):
        """Mark an appointment as completed."""
        appointment = AppointmentService.get_appointment(appointment_id)

        if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED):
            raise AppointmentServiceError(
                "Only scheduled or rescheduled appointments can be marked as completed."
            )

        appointment.status = Appointment.Status.COMPLETED
        if completed_by:
            appointment.updated_by = completed_by
        appointment.save()
        return appointment

    @staticmethod
    def get_upcoming(user):
        """
        Return upcoming scheduled appointments for a user.
        Staff see their own appointments; clients see theirs.
        """
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

        # Admin sees all
        return base_qs

    @staticmethod
    def get_client_sessions_count(client_id):
        """Return the count of completed appointments for a client."""
        return Appointment.active_objects.filter(
            client_id=client_id,
            status=Appointment.Status.COMPLETED,
        ).count()

    @staticmethod
    def get_all_appointments():
        """Return all non-deleted appointments."""
        return Appointment.active_objects.all()

    @staticmethod
    def get_staff_appointments(staff_user):
        """Return all non-deleted appointments for a specific staff member."""
        return Appointment.active_objects.filter(staff=staff_user)

    @staticmethod
    def get_client_appointments(client):
        """Return all non-deleted appointments for a specific client."""
        return Appointment.active_objects.filter(client=client)
