import datetime

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment


class AppointmentServiceError(Exception):
    """Raised when an appointment service operation fails."""
    pass


def _staff_is_on_leave(staff_user, target_date):
    """Return the active LEAVE AttendanceMark for staff on date, or None."""
    from attendance.models import AttendanceMark
    return AttendanceMark.active_objects.filter(
        user=staff_user,
        date=target_date,
        status=AttendanceMark.Status.LEAVE,
    ).first()


class AppointmentService:
    """Service layer for appointment operations."""

    @staticmethod
    def create_appointment(data, created_by=None):
        """Create and return a new Appointment.

        If the assigned staff has a LEAVE mark for the date, flag the
        appointment for reassignment so admin sees it in the banner.
        """
        appointment = Appointment(**data)
        if created_by:
            appointment.created_by = created_by
        appointment.calculate_price()
        appointment.full_clean()

        leave_mark = _staff_is_on_leave(appointment.staff, appointment.date)
        if leave_mark:
            appointment.needs_reassignment = True
            appointment.reassignment_reason = (
                f"Staff is absent on {appointment.date:%d %b} — please reassign."
            )

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
            session_price=appointment.session_price,
            date=new_date,
            start_time=new_start_time,
            end_time=new_end_time or appointment.end_time,
            status=Appointment.Status.SCHEDULED,
            notes=f"Rescheduled from {appointment.date.strftime('%d %b %Y')}",
            created_by=updated_by,
        )

        leave_mark = _staff_is_on_leave(appointment.staff, new_date)
        if leave_mark:
            new_appointment.needs_reassignment = True
            new_appointment.reassignment_reason = (
                f"Staff is absent on {new_date:%d %b} — please reassign."
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

        # Block reassignment to staff who are on leave for that date.
        leave_mark = _staff_is_on_leave(new_staff, appointment.date)
        if leave_mark:
            name = new_staff.get_full_name() or new_staff.mobile_number
            raise AppointmentServiceError(
                f"{name} is absent on {appointment.date:%d %b %Y}. Pick another staff member."
            )

        old_staff_name = appointment.staff.get_full_name() or appointment.staff.mobile_number
        new_staff_name = new_staff.get_full_name() or new_staff.mobile_number

        remark = f"[Reassigned from {old_staff_name} to {new_staff_name} on {timezone.localtime().strftime('%d %b %Y, %I:%M %p')}]"
        appointment.staff = new_staff
        appointment.notes = (appointment.notes + '\n' if appointment.notes else '') + remark
        appointment.needs_reassignment = False
        appointment.reassignment_reason = ''
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

    @staticmethod
    def get_pending_reassignments(target_date):
        """Appointments on *target_date* that need a new staff assignment."""
        return (
            Appointment.active_objects
            .filter(date=target_date, needs_reassignment=True)
            .exclude(status=Appointment.Status.CANCELLED)
            .select_related('client', 'staff', 'therapy_type')
            .order_by('start_time')
        )

    # ---- Daily schedule grid helpers ---------------------------------------

    # Default time slots — 9:00 AM to 7:30 PM in 45-minute intervals.
    DEFAULT_SLOT_START_MINUTES = 9 * 60       # 09:00
    DEFAULT_SLOT_END_MINUTES = 20 * 60 + 15   # 20:15 (last slot starts 19:30)
    DEFAULT_SLOT_DURATION = 45

    @staticmethod
    def get_time_slots():
        """Return list of (datetime.time, label) tuples for the grid rows."""
        slots = []
        minute = AppointmentService.DEFAULT_SLOT_START_MINUTES
        while minute < AppointmentService.DEFAULT_SLOT_END_MINUTES:
            t = datetime.time(hour=minute // 60, minute=minute % 60)
            label = t.strftime('%I:%M %p').lstrip('0')
            slots.append((t, label))
            minute += AppointmentService.DEFAULT_SLOT_DURATION
        return slots

    @staticmethod
    def get_day_schedule(target_date):
        """
        Return structured data for the day-wise grid:
          {
            'date': date,
            'staff': [user, ...],
            'slots': [(time, label), ...],
            'grid': { (staff_id, time): appointment },
            'absent': [appointment, ...],
            'group': [appointment, ...],
          }
        """
        from accounts.models import User

        staff = list(
            User.objects.filter(
                role__in=[User.Role.STAFF, User.Role.ADMIN],
                is_active=True,
            ).order_by('first_name', 'last_name')
        )
        slots = AppointmentService.get_time_slots()

        appointments = (
            Appointment.active_objects
            .filter(date=target_date)
            .select_related('client', 'staff', 'therapy_type')
        )

        grid = {}
        absent = []
        group = []
        for appt in appointments:
            if appt.is_absent:
                absent.append(appt)
                continue
            if appt.is_group:
                group.append(appt)
                continue
            grid[(appt.staff_id, appt.start_time.replace(second=0, microsecond=0))] = appt

        return {
            'date': target_date,
            'staff': staff,
            'slots': slots,
            'grid': grid,
            'absent': absent,
            'group': group,
        }

    @staticmethod
    def copy_day(source_date, target_date, created_by=None):
        """Duplicate all non-cancelled appointments from source_date to target_date."""
        source = Appointment.active_objects.filter(
            date=source_date,
        ).exclude(status=Appointment.Status.CANCELLED)

        created = 0
        leave_cache = {}  # {staff_id: AttendanceMark|None} for target_date

        for appt in source:
            exists = Appointment.active_objects.filter(
                date=target_date,
                staff=appt.staff,
                start_time=appt.start_time,
                client=appt.client,
            ).exists()
            if exists:
                continue

            if appt.staff_id not in leave_cache:
                leave_cache[appt.staff_id] = _staff_is_on_leave(appt.staff, target_date)
            leave_mark = leave_cache[appt.staff_id]

            Appointment.objects.create(
                client=appt.client,
                staff=appt.staff,
                therapy_type=appt.therapy_type,
                session_price=appt.session_price,
                date=target_date,
                start_time=appt.start_time,
                end_time=appt.end_time,
                status=Appointment.Status.SCHEDULED,
                is_group=appt.is_group,
                needs_reassignment=bool(leave_mark),
                reassignment_reason=(
                    f"Staff is absent on {target_date:%d %b} — please reassign."
                    if leave_mark else ''
                ),
                created_by=created_by,
            )
            created += 1
        return created

    @staticmethod
    def quick_create(client, staff, therapy_type, date, start_time, created_by=None,
                     is_group=False, notes=''):
        """Create a single appointment for the schedule grid."""
        if not therapy_type:
            raise AppointmentServiceError("Therapy type is required.")

        duration = datetime.timedelta(minutes=therapy_type.duration)
        end_dt = (datetime.datetime.combine(date, start_time) + duration)
        end_time = end_dt.time()

        conflict = Appointment.active_objects.filter(
            date=date,
            staff=staff,
            start_time=start_time,
        ).exclude(status=Appointment.Status.CANCELLED).exists()
        if conflict and not is_group:
            raise AppointmentServiceError(
                "This staff already has an appointment at that time."
            )

        appointment = Appointment(
            client=client,
            staff=staff,
            therapy_type=therapy_type,
            date=date,
            start_time=start_time,
            end_time=end_time,
            is_group=is_group,
            notes=notes,
            created_by=created_by,
        )
        appointment.calculate_price()

        leave_mark = _staff_is_on_leave(staff, date)
        if leave_mark:
            appointment.needs_reassignment = True
            appointment.reassignment_reason = (
                f"Staff is absent on {date:%d %b} — please reassign."
            )

        appointment.save()
        return appointment

    @staticmethod
    def mark_absent(appointment_id, updated_by=None):
        appointment = AppointmentService.get_appointment(appointment_id)
        appointment.is_absent = True
        if updated_by:
            appointment.updated_by = updated_by
        appointment.save()
        return appointment


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
    duration_label = f"{appointment.therapy_type.duration} min"
    description = f"{therapy_name} ({duration_label}) - {appointment.date.strftime('%d %b %Y')}"

    BillingService.append_daily_session(
        client=appointment.client,
        appointment=appointment,
        description=description,
        amount=appointment.session_price,
        created_by=created_by,
    )
