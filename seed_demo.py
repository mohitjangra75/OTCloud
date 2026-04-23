"""
Seed demo data covering every UI state across the appointments & attendance flows.

Run: python manage.py shell < seed_demo.py
or   python -c "exec(open('seed_demo.py').read())" inside manage.py shell
"""
from datetime import datetime, date, time, timedelta

from django.utils import timezone

from accounts.models import User
from clients.models import Client
from appointments.models import Appointment, TherapyType
from attendance.models import AttendanceLog, AttendanceMark

TODAY = timezone.localdate()
TOMORROW = TODAY + timedelta(days=1)
DAY_AFTER = TODAY + timedelta(days=2)

IST = timezone.get_current_timezone()


def _dt(d, hh, mm=0):
    return timezone.make_aware(datetime(d.year, d.month, d.day, hh, mm), IST)


def _t(hh, mm=0):
    return time(hh, mm)


# ---------------------------------------------------------------------------
# 0. Look up fixtures
# ---------------------------------------------------------------------------
admin = User.objects.get(mobile_number='9306123897')
amit = User.objects.get(mobile_number='9000000003')       # Amit Patel
priya = User.objects.get(mobile_number='9000000002')      # Priya Verma
rahul = User.objects.get(mobile_number='9000000001')      # Rahul Sharma

neha = Client.active_objects.get(mobile_number='8000000001')     # Neha Gupta
rohan = Client.active_objects.get(mobile_number='8000000002')    # Rohan Singh

ot30 = TherapyType.active_objects.get(name='Occupational Therapy', duration=30)
ot60 = TherapyType.active_objects.get(name='Occupational Therapy', duration=60)
neuro30 = TherapyType.active_objects.get(name='Neuro Therapy', duration=30)
neuro60 = TherapyType.active_objects.get(name='Neuro Therapy', duration=60)
hear30 = TherapyType.active_objects.get(name='Hearing Therapy', duration=30)
hear60 = TherapyType.active_objects.get(name='Hearing Therapy', duration=60)
sens30 = TherapyType.active_objects.get(name='Sensory Integration Therapy', duration=30)


# ---------------------------------------------------------------------------
# 1. Clean slate
# ---------------------------------------------------------------------------
deleted_appts, _ = Appointment.objects.all().delete()
deleted_marks, _ = AttendanceMark.objects.all().delete()
# Only wipe today's/future logs so historical data is preserved
deleted_logs, _ = AttendanceLog.objects.filter(date__gte=TODAY).delete()
print(f"Cleaned: {deleted_appts} appointments, {deleted_marks} marks, {deleted_logs} logs.")


# ---------------------------------------------------------------------------
# 2. Attendance marks
# ---------------------------------------------------------------------------
AttendanceMark.objects.create(
    user=rahul, date=TODAY, status=AttendanceMark.Status.LEAVE,
    notes='Family commitment', created_by=rahul,
)
AttendanceMark.objects.create(
    user=priya, date=TOMORROW, status=AttendanceMark.Status.HALF_DAY,
    notes='Doctor appointment in the afternoon', created_by=priya,
)
AttendanceMark.objects.create(
    user=rahul, date=DAY_AFTER, status=AttendanceMark.Status.LEAVE,
    notes='Family commitment (continued)', created_by=rahul,
)
print("Marks created: Rahul on leave today & day-after, Priya half-day tomorrow.")


# ---------------------------------------------------------------------------
# 3. Attendance logs for TODAY (drives Team Day statuses)
# ---------------------------------------------------------------------------
# Amit — has 2 sessions, currently active (second one has no check-out)
AttendanceLog.objects.create(
    user=amit,
    check_in_time=_dt(TODAY, 9, 5),
    check_out_time=_dt(TODAY, 13, 0),
    date=TODAY,
)
AttendanceLog.objects.create(
    user=amit,
    check_in_time=_dt(TODAY, 14, 0),
    check_out_time=None,
    date=TODAY,
)

# Priya — full day, will render as Present (8h)
AttendanceLog.objects.create(
    user=priya,
    check_in_time=_dt(TODAY, 9, 30),
    check_out_time=_dt(TODAY, 12, 30),
    date=TODAY,
)
AttendanceLog.objects.create(
    user=priya,
    check_in_time=_dt(TODAY, 13, 30),
    check_out_time=_dt(TODAY, 17, 30),
    date=TODAY,
)

# Rahul — no logs (on leave)
print("Attendance logs created: Amit (active), Priya (8h present), Rahul (leave).")


# ---------------------------------------------------------------------------
# 4. Today's appointments — one of every UI state
# ---------------------------------------------------------------------------

def mk_appt(**kw):
    """Create with explicit end_time computed from therapy duration if missing."""
    if 'end_time' not in kw and kw.get('therapy_type') and kw.get('start_time'):
        start = kw['start_time']
        dur = timedelta(minutes=kw['therapy_type'].duration)
        end_dt = datetime.combine(kw['date'], start) + dur
        kw['end_time'] = end_dt.time()
    return Appointment.objects.create(**kw)


# (A) Normal scheduled — green cell
mk_appt(
    client=neha, staff=amit, therapy_type=ot30,
    date=TODAY, start_time=_t(9, 0),
    status=Appointment.Status.SCHEDULED,
    notes='First slot of the day', created_by=admin,
)

# (B) Normal scheduled — green
mk_appt(
    client=rohan, staff=amit, therapy_type=ot30,
    date=TODAY, start_time=_t(9, 45),
    status=Appointment.Status.SCHEDULED,
    created_by=admin,
)

# (C) Normal scheduled (60 min) — green, spans longer
mk_appt(
    client=neha, staff=priya, therapy_type=neuro60,
    date=TODAY, start_time=_t(10, 30),
    status=Appointment.Status.SCHEDULED,
    created_by=admin,
)

# (D) NEEDS REASSIGNMENT — Rahul on leave → amber cell + reassignment banner
mk_appt(
    client=rohan, staff=rahul, therapy_type=hear30,
    date=TODAY, start_time=_t(11, 15),
    status=Appointment.Status.SCHEDULED,
    needs_reassignment=True,
    reassignment_reason=f"Staff is on leave on {TODAY:%d %b} — please reassign.",
    created_by=admin,
)

# (E) NEEDS REASSIGNMENT (second one for the same staff)
mk_appt(
    client=neha, staff=rahul, therapy_type=sens30,
    date=TODAY, start_time=_t(12, 0),
    status=Appointment.Status.SCHEDULED,
    needs_reassignment=True,
    reassignment_reason=f"Staff is on leave on {TODAY:%d %b} — please reassign.",
    created_by=admin,
)

# (F) COMPLETED — blue cell
mk_appt(
    client=rohan, staff=amit, therapy_type=ot30,
    date=TODAY, start_time=_t(13, 30),
    status=Appointment.Status.COMPLETED,
    notes='Session went well. Good progress on gross motor.',
    created_by=admin,
)

# (G) CANCELLED — red strikethrough
mk_appt(
    client=neha, staff=priya, therapy_type=hear60,
    date=TODAY, start_time=_t(15, 0),
    status=Appointment.Status.CANCELLED,
    cancellation_reason='Client cancelled due to travel.',
    created_by=admin,
)

# (H) RESCHEDULED — amber cell
mk_appt(
    client=neha, staff=amit, therapy_type=sens30,
    date=TODAY, start_time=_t(16, 30),
    status=Appointment.Status.RESCHEDULED,
    notes='Rescheduled to 26 Apr on client request.',
    created_by=admin,
)

# (I) GROUP SESSION — shows in Group side panel, not in grid
mk_appt(
    client=rohan, staff=priya, therapy_type=neuro30,
    date=TODAY, start_time=_t(17, 15),
    status=Appointment.Status.SCHEDULED,
    is_group=True,
    notes='Group circle-time session.',
    created_by=admin,
)

# (J) CLIENT ABSENT — shows in Absent side panel
mk_appt(
    client=neha, staff=amit, therapy_type=ot30,
    date=TODAY, start_time=_t(18, 0),
    status=Appointment.Status.SCHEDULED,
    is_absent=True,
    notes='Client no-show.',
    created_by=admin,
)


# ---------------------------------------------------------------------------
# 5. Tomorrow's appointments — mixed
# ---------------------------------------------------------------------------
mk_appt(
    client=neha, staff=priya, therapy_type=hear60,
    date=TOMORROW, start_time=_t(9, 0),
    status=Appointment.Status.SCHEDULED,
    notes='Morning session before Priya half-day.',
    created_by=admin,
)
mk_appt(
    client=rohan, staff=amit, therapy_type=neuro30,
    date=TOMORROW, start_time=_t(11, 0),
    status=Appointment.Status.SCHEDULED,
    created_by=admin,
)
# Rahul's tomorrow is free (leave only today and day-after). No appt.

# Day after: Rahul on leave, so any appt for him should be flagged
mk_appt(
    client=neha, staff=rahul, therapy_type=ot60,
    date=DAY_AFTER, start_time=_t(10, 0),
    status=Appointment.Status.SCHEDULED,
    needs_reassignment=True,
    reassignment_reason=f"Staff is on leave on {DAY_AFTER:%d %b} — please reassign.",
    created_by=admin,
)


print("-" * 60)
print(f"Seeded {Appointment.objects.count()} appointments and "
      f"{AttendanceMark.objects.count()} marks.")
print("Today states covered: scheduled, needs-reassignment, completed, "
      "cancelled, rescheduled, group, client-absent.")
print("Team Day today: Amit (active), Priya (present 8h), Rahul (leave).")
print("Tomorrow: 2 appts; Priya marked half-day.")
