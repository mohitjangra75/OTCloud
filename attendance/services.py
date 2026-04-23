import datetime
from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from attendance.models import AttendanceLog, AttendanceMark

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
    # Explicit attendance marks (admin: mark absent / half-day in advance)
    # ------------------------------------------------------------------

    MARK_MAX_DAYS_AHEAD = 7

    @classmethod
    def mark(cls, user, date, status, marked_by=None, notes=''):
        """Create/update an AttendanceMark and cascade effects on appointments."""
        today = timezone.now().date()
        if date < today:
            raise AttendanceError("Cannot mark attendance for past dates.")
        if (date - today).days > cls.MARK_MAX_DAYS_AHEAD:
            raise AttendanceError(
                f"Marks can only be set up to {cls.MARK_MAX_DAYS_AHEAD} days ahead."
            )
        if status not in AttendanceMark.Status.values:
            raise AttendanceError("Invalid status.")

        mark, _created = AttendanceMark.objects.update_or_create(
            user=user, date=date,
            defaults={
                'status': status,
                'notes': notes,
                'updated_by': marked_by,
                'is_deleted': False,
            },
        )
        if _created and marked_by:
            mark.created_by = marked_by
            mark.save(update_fields=['created_by'])

        # Cascade: full leave → suspend appointments for that day
        if status == AttendanceMark.Status.LEAVE:
            _suspend_staff_appointments(user, date, reason="Staff absent")
        else:
            # HALF_DAY does not auto-suspend; clear any prior flag
            _unsuspend_staff_appointments(user, date)
        return mark

    @classmethod
    def unmark(cls, user, date):
        """Remove the mark (if any) and clear any pending reassignment flags."""
        AttendanceMark.active_objects.filter(user=user, date=date).update(is_deleted=True)
        _unsuspend_staff_appointments(user, date)

    @staticmethod
    def get_mark(user, date):
        return AttendanceMark.active_objects.filter(user=user, date=date).first()

    @staticmethod
    def get_marks_map(date):
        """Return {user_id: mark} for all active marks on a given date."""
        return {
            m.user_id: m
            for m in AttendanceMark.active_objects.filter(date=date)
        }

    # ------------------------------------------------------------------
    # Team-wide (admin) views
    # ------------------------------------------------------------------

    PRESENT_HOURS_THRESHOLD = timedelta(hours=6)
    HALF_DAY_HOURS_THRESHOLD = timedelta(hours=3)

    @classmethod
    def _status_for_total(cls, total, has_logs, is_future):
        """Derive a day-status label from total hours worked."""
        if is_future:
            return 'upcoming'
        if not has_logs:
            return 'absent'
        if total >= cls.PRESENT_HOURS_THRESHOLD:
            return 'present'
        if total >= cls.HALF_DAY_HOURS_THRESHOLD:
            return 'half-day'
        return 'short'

    @classmethod
    def get_day_attendance(cls, target_date):
        """
        Return attendance data for every active staff/admin on *target_date*.

        Each entry:
            {
              'user', 'logs', 'total',
              'check_in', 'check_out', 'is_active',
              'status', 'mark',
            }
        Status prioritises an explicit AttendanceMark over derived values.
        """
        from accounts.models import User

        today = timezone.now().date()
        is_future = target_date > today

        users = User.objects.filter(
            role__in=[User.Role.STAFF, User.Role.ADMIN],
            is_active=True,
        ).order_by('first_name', 'last_name')

        logs_by_user = {}
        qs = AttendanceLog.active_objects.filter(date=target_date).order_by('check_in_time')
        for log in qs:
            logs_by_user.setdefault(log.user_id, []).append(log)

        marks_map = cls.get_marks_map(target_date)

        rows = []
        for u in users:
            user_logs = logs_by_user.get(u.id, [])
            total = timedelta()
            for lg in user_logs:
                if lg.duration:
                    total += lg.duration
            first_in = user_logs[0].check_in_time if user_logs else None
            last_out = None
            for lg in reversed(user_logs):
                if lg.check_out_time:
                    last_out = lg.check_out_time
                    break
            is_active = any(lg.check_out_time is None for lg in user_logs)

            mark = marks_map.get(u.id)
            if mark:
                # Leave + absent share one visible status. Internal enum stays 'leave'.
                status = 'half_day' if mark.status == AttendanceMark.Status.HALF_DAY else 'absent'
            else:
                status = cls._status_for_total(total, bool(user_logs), is_future)

            rows.append({
                'user': u,
                'logs': user_logs,
                'total': total,
                'check_in': first_in,
                'check_out': last_out,
                'is_active': is_active,
                'status': status,
                'mark': mark,
            })
        return rows

    @classmethod
    def get_month_stats(cls, year, month):
        """
        Return aggregated attendance per user for a calendar month.

        Each entry:
            {
              'user', 'total', 'total_display',
              'days_present', 'days_absent', 'days_half',
              'expected_days', 'avg_per_day',
            }
        Expected workdays = Mon–Sat up to today (if current month) or full month.
        """
        import calendar
        from collections import defaultdict
        from accounts.models import User

        today = timezone.now().date()
        days_in_month = calendar.monthrange(year, month)[1]

        # Count Mon–Sat workdays up to today (if current month) else full month
        def _is_workday(d):
            return d.weekday() != 6  # skip Sunday

        expected_days = 0
        for d_num in range(1, days_in_month + 1):
            d = datetime.date(year, month, d_num)
            if d > today:
                break
            if _is_workday(d):
                expected_days += 1

        users = User.objects.filter(
            role__in=[User.Role.STAFF, User.Role.ADMIN],
            is_active=True,
        ).order_by('first_name', 'last_name')

        # Batch fetch logs for the whole month and bucket by user+date
        qs = AttendanceLog.active_objects.filter(
            date__year=year, date__month=month,
        )

        by_user_date = defaultdict(lambda: defaultdict(timedelta))
        for log in qs:
            if log.duration:
                by_user_date[log.user_id][log.date] += log.duration

        rows = []
        for u in users:
            user_days = by_user_date.get(u.id, {})
            total = timedelta()
            present = 0
            half = 0
            for d, dur in user_days.items():
                total += dur
                if dur >= cls.PRESENT_HOURS_THRESHOLD:
                    present += 1
                elif dur >= cls.HALF_DAY_HOURS_THRESHOLD:
                    half += 1
                else:
                    # has logs but under half-day threshold — count as half
                    half += 1
            absent = max(0, expected_days - present - half)
            avg = (total / present) if present else timedelta()
            rows.append({
                'user': u,
                'total': total,
                'days_present': present,
                'days_half': half,
                'days_absent': absent,
                'expected_days': expected_days,
                'avg_per_day': avg,
            })
        return rows

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


# ---------------------------------------------------------------------------
# Cross-app cascades (appointments)
# ---------------------------------------------------------------------------

def _suspend_staff_appointments(staff_user, target_date, reason=''):
    """Flag scheduled appointments for *staff_user* on *target_date* as needing reassignment."""
    from appointments.models import Appointment

    Appointment.active_objects.filter(
        staff=staff_user,
        date=target_date,
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED],
    ).update(
        needs_reassignment=True,
        reassignment_reason=reason or 'Staff unavailable',
    )


def _unsuspend_staff_appointments(staff_user, target_date):
    """Clear the reassignment flag for *staff_user*'s still-assigned appointments on *target_date*."""
    from appointments.models import Appointment

    Appointment.active_objects.filter(
        staff=staff_user,
        date=target_date,
        needs_reassignment=True,
    ).update(
        needs_reassignment=False,
        reassignment_reason='',
    )
