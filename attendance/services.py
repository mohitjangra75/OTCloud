import datetime
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from attendance.models import AttendanceLog

IST = datetime.timezone(timedelta(hours=5, minutes=30))


class AttendanceError(Exception):
    """Base exception for attendance operations."""
    pass


class AttendanceService:
    """Service layer for all attendance check-in / check-out operations."""

    @staticmethod
    def _get_office_times():
        """Return office start and end as time objects from settings."""
        start_h, start_m = map(int, settings.OFFICE_START_TIME.split(':'))
        end_h, end_m = map(int, settings.OFFICE_END_TIME.split(':'))
        return datetime.time(start_h, start_m), datetime.time(end_h, end_m)

    @staticmethod
    def _now_ist():
        """Return the current datetime in IST."""
        return timezone.now().astimezone(IST)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @classmethod
    def check_in(cls, user):
        """
        Create a new attendance log for *user*.

        Raises AttendanceError if:
        - The user already has an open (un-checked-out) session.
        - The current IST time is outside office hours.
        """
        now = cls._now_ist()
        office_start, office_end = cls._get_office_times()

        if now.time() < office_start or now.time() > office_end:
            raise AttendanceError(
                f"Check-in is only allowed during office hours "
                f"({office_start.strftime('%I:%M %p')} – {office_end.strftime('%I:%M %p')} IST)."
            )

        open_session = AttendanceLog.active_objects.filter(
            user=user,
            check_out_time__isnull=True,
        ).first()
        if open_session:
            raise AttendanceError("You already have an active session. Please check out first.")

        log = AttendanceLog.objects.create(
            user=user,
            check_in_time=now,
            date=now.date(),
            created_by=user,
        )
        return log

    @classmethod
    def check_out(cls, user):
        """
        Close the currently open attendance session for *user*.

        Raises AttendanceError if no open session exists.
        Returns the updated AttendanceLog with duration populated.
        """
        open_session = AttendanceLog.active_objects.filter(
            user=user,
            check_out_time__isnull=True,
        ).order_by('-check_in_time').first()

        if not open_session:
            raise AttendanceError("No active session found. Please check in first.")

        now = cls._now_ist()
        open_session.check_out_time = now
        open_session.updated_by = user
        open_session.save()  # duration calculated in model.save()
        return open_session

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_daily_logs(user, date):
        """Return all attendance sessions for *user* on *date*, newest first."""
        return AttendanceLog.active_objects.filter(
            user=user,
            date=date,
        ).order_by('-check_in_time')

    @staticmethod
    def get_daily_hours(user, date):
        """Return total duration worked on *date* as a timedelta (or 0)."""
        result = AttendanceLog.active_objects.filter(
            user=user,
            date=date,
            duration__isnull=False,
        ).aggregate(total=Sum('duration'))
        return result['total'] or timedelta()

    @staticmethod
    def get_monthly_hours(user, year, month):
        """Return total duration worked in a calendar month as a timedelta."""
        result = AttendanceLog.active_objects.filter(
            user=user,
            date__year=year,
            date__month=month,
            duration__isnull=False,
        ).aggregate(total=Sum('duration'))
        return result['total'] or timedelta()

    # ------------------------------------------------------------------
    # Auto check-out
    # ------------------------------------------------------------------

    @classmethod
    def auto_checkout(cls):
        """
        Automatically check out every open session.

        Intended to be called via a management command / cron at 7 PM IST.
        Sets check_out_time to the office end time on the session's date.
        """
        _, office_end = cls._get_office_times()
        open_sessions = AttendanceLog.active_objects.filter(
            check_out_time__isnull=True,
        )
        count = 0
        for session in open_sessions:
            end_dt = datetime.datetime.combine(
                session.date, office_end, tzinfo=IST,
            )
            session.check_out_time = end_dt
            session.notes = (session.notes + ' ' if session.notes else '') + '[Auto checkout]'
            session.save()
            count += 1
        return count

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @staticmethod
    def get_current_status(user):
        """
        Return a dict describing the user's current attendance state.

        Keys:
            checked_in (bool)
            current_session (AttendanceLog | None)
        """
        session = AttendanceLog.active_objects.filter(
            user=user,
            check_out_time__isnull=True,
        ).order_by('-check_in_time').first()

        return {
            'checked_in': session is not None,
            'current_session': session,
        }
