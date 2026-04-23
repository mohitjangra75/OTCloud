"""
Sync appointments with active LEAVE attendance marks.

Safety net that catches appointments which slipped through the preventive
validation (e.g. created via Django admin, bulk import, or race conditions
where the mark landed after the appointment). Intended to run ~2x/day.

Usage:
    python manage.py sync_leave_appointments
    python manage.py sync_leave_appointments --days-ahead 14  # default 7
    python manage.py sync_leave_appointments --dry-run
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from appointments.models import Appointment
from attendance.models import AttendanceMark


class Command(BaseCommand):
    help = "Flag scheduled appointments for reassignment when the assigned staff is on LEAVE."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead', type=int, default=7,
            help='How many days ahead to scan (default: 7).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report changes without writing.',
        )

    def handle(self, *args, **opts):
        today = timezone.now().date()
        horizon = today + timedelta(days=opts['days_ahead'])
        dry = opts['dry_run']

        marks = AttendanceMark.active_objects.filter(
            status=AttendanceMark.Status.LEAVE,
            date__gte=today,
            date__lte=horizon,
        ).select_related('user')

        total_flagged = 0
        total_unflagged = 0

        # 1. Flag: scheduled appointments that should be flagged but aren't
        for mark in marks:
            qs = Appointment.active_objects.filter(
                staff=mark.user,
                date=mark.date,
                status__in=[Appointment.Status.SCHEDULED, Appointment.Status.RESCHEDULED],
                needs_reassignment=False,
            )
            count = qs.count()
            if count:
                msg = (f"[flag] {mark.user} absent {mark.date}: "
                       f"{count} appointment(s) need reassignment")
                self.stdout.write(msg)
                if not dry:
                    qs.update(
                        needs_reassignment=True,
                        reassignment_reason=f"Staff absent ({mark.date:%d %b})",
                    )
                total_flagged += count

        # 2. Unflag: appointments flagged but their staff's LEAVE mark no longer exists
        flagged_qs = Appointment.active_objects.filter(
            needs_reassignment=True,
            date__gte=today,
            date__lte=horizon,
        )
        for appt in flagged_qs:
            still_on_leave = AttendanceMark.active_objects.filter(
                user=appt.staff,
                date=appt.date,
                status=AttendanceMark.Status.LEAVE,
            ).exists()
            if not still_on_leave:
                self.stdout.write(
                    f"[unflag] {appt.staff} no longer absent {appt.date}: "
                    f"clearing reassignment flag on appointment #{appt.pk}"
                )
                if not dry:
                    appt.needs_reassignment = False
                    appt.reassignment_reason = ''
                    appt.save(update_fields=['needs_reassignment', 'reassignment_reason'])
                total_unflagged += 1

        summary = f"Done. flagged={total_flagged} unflagged={total_unflagged}"
        if dry:
            summary += " (dry-run, no writes)"
        self.stdout.write(self.style.SUCCESS(summary))
