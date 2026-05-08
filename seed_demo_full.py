"""
Comprehensive demo seed.

Keeps: User (admin/staff), Client, TherapyType.
Generates everything else with a mix of past and future dates and varied statuses
so every screen + filter has something interesting to show.

Run via: python manage.py shell < seed_demo_full.py
"""
import os
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OTCloud.settings')
django.setup()

from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment, TherapyType
from attendance.models import AttendanceLog, AttendanceMark
from billing.models import Expense, Invoice, MonthlyBill
from billing.services import BillingService, InvoiceService
from clients.models import Client
from lms.models import FollowUp, Lead
from notifications.models import Notification
from salary.models import MonthlySalary, SalarySetting
from salary.services import SalaryService

random.seed(42)
TODAY = date.today()
print(f"Seeding for today = {TODAY}")

admins = list(User.objects.filter(role='admin', is_active=True).order_by('id'))
staff = list(User.objects.filter(role='staff', is_active=True).order_by('id'))
clients = list(Client.active_objects.order_by('id'))
therapies = list(TherapyType.active_objects.order_by('id'))

if not admins or not staff or not clients or not therapies:
    raise SystemExit("Need at least 1 admin, 1 staff, 1 client, 1 therapy type to seed.")

main_admin = admins[0]
print(f"  admins={len(admins)} staff={len(staff)} clients={len(clients)} therapy_types={len(therapies)}")

# ===========================================================
# 1. SALARY SETTINGS
# ===========================================================
print("\n[1/8] Salary settings...")
for s in staff:
    SalarySetting.objects.update_or_create(
        employee=s,
        defaults={
            'base_monthly_salary': Decimal(random.choice(['22000', '25000', '28000'])),
            'deduction_per_absent_day': Decimal(random.choice(['800', '1000', '1200'])),
            'sessions_target_per_week': random.choice([18, 20, 24]),
            'incentive_per_extra_session': Decimal(random.choice(['100', '150', '200'])),
            'created_by': main_admin,
        },
    )
for a in admins:
    SalarySetting.objects.update_or_create(
        employee=a,
        defaults={
            'base_monthly_salary': Decimal('45000'),
            'deduction_per_absent_day': Decimal('1500'),
            'sessions_target_per_week': 0,
            'incentive_per_extra_session': Decimal('0'),
            'created_by': main_admin,
        },
    )
print(f"  -> {SalarySetting.objects.count()} salary settings")

# ===========================================================
# 2. ATTENDANCE LOGS — last 60 days, 90% present
# ===========================================================
print("\n[2/8] Attendance logs...")
attendance_count = 0
for emp in admins + staff:
    for offset in range(60):
        d = TODAY - timedelta(days=offset)
        if d.weekday() == 6:  # Sunday off
            continue
        if random.random() < 0.92:
            ci = timezone.make_aware(datetime.combine(d, time(9, random.randint(0, 30))))
            co_hour = 18 if random.random() < 0.85 else 19
            co = timezone.make_aware(datetime.combine(d, time(co_hour, random.randint(0, 45))))
            AttendanceLog.objects.create(
                user=emp, date=d, check_in_time=ci, check_out_time=co,
            )
            attendance_count += 1
print(f"  -> {attendance_count} attendance logs")

# ===========================================================
# 3. ATTENDANCE MARKS — sprinkle half-day + leave
# ===========================================================
print("\n[3/8] Attendance marks (half-days + leaves)...")
mark_count = 0
for s in staff:
    chosen_offsets = random.sample(range(2, 55), 5)
    for offset in chosen_offsets:
        d = TODAY - timedelta(days=offset)
        if d.weekday() == 6:
            continue
        status = random.choice(['half_day', 'leave', 'half_day', 'leave', 'leave'])
        AttendanceMark.objects.update_or_create(
            user=s, date=d,
            defaults={'status': status, 'notes': 'Demo mark'},
        )
        mark_count += 1
# Future leave for one staff member
for s in random.sample(staff, min(2, len(staff))):
    future = TODAY + timedelta(days=random.randint(2, 6))
    if future.weekday() != 6:
        AttendanceMark.objects.update_or_create(
            user=s, date=future,
            defaults={'status': 'leave', 'notes': 'Planned leave'},
        )
        mark_count += 1
print(f"  -> {mark_count} attendance marks")

# ===========================================================
# 4. APPOINTMENTS — 90 days past + 60 days future
# ===========================================================
print("\n[4/8] Appointments...")
slot_hours = [9, 10, 11, 12, 14, 15, 16, 17]
created = 0
session_pairs = []  # (client, therapy_type, date, status, staff)

for offset in range(-90, 60):
    d = TODAY + timedelta(days=offset)
    if d.weekday() == 6:
        continue
    # Pick 3-6 sessions per working day
    for h in random.sample(slot_hours, random.randint(3, 6)):
        c = random.choice(clients)
        s = random.choice(staff)
        t = random.choice(therapies)
        end = (datetime.combine(d, time(h, 0)) + timedelta(minutes=t.duration)).time()
        is_group = random.random() < 0.07
        if d < TODAY:
            status = random.choices(
                ['completed', 'cancelled', 'rescheduled'],
                weights=[82, 12, 6],
            )[0]
        elif d == TODAY:
            status = random.choices(['completed', 'scheduled'], weights=[40, 60])[0]
        else:
            status = 'scheduled'
        # ~5% needs_reassignment for upcoming
        needs_reassign = (d > TODAY and random.random() < 0.05)
        appt = Appointment.objects.create(
            client=c, staff=s, therapy_type=t,
            date=d, start_time=time(h, 0), end_time=end,
            status=status, is_group=is_group,
            session_price=t.price,
            needs_reassignment=needs_reassign,
            reassignment_reason='Staff on leave that day' if needs_reassign else '',
            notes='',
        )
        created += 1
        session_pairs.append((c, t, d, status, s))
print(f"  -> {created} appointments")

# ===========================================================
# 5. EXPENSES (reimbursements) — last 60 days, mix of pending + paid
# ===========================================================
print("\n[5/8] Expenses / Reimbursements...")
items = ['Travel to client', 'Stationery', 'Internet bill', 'Snacks', 'Auto rickshaw',
         'Printer toner', 'Lunch with client', 'Mobile recharge', 'Cleaning supplies',
         'Bank charges', 'WhatsApp business']
expense_count = 0
for offset in range(0, 60, 3):
    d = TODAY - timedelta(days=offset)
    emp = random.choice(staff + admins)
    paid_by = main_admin
    Expense.objects.create(
        date=d,
        category='reimbursement',
        item=random.choice(items),
        amount=Decimal(random.choice([200, 350, 500, 750, 1000, 1500, 2200, 3500])),
        payment_mode=random.choice(['cash', 'upi', 'bank']),
        paid_to_employee=emp,
        paid_by=paid_by,
        status=random.choice(['pending', 'reimbursed', 'reimbursed', 'reimbursed']),
        remarks=random.choice(['', '', 'urgent', 'monthly recurring', 'site visit']),
        created_by=emp,
    )
    expense_count += 1
print(f"  -> {expense_count} expense entries")

# ===========================================================
# 6. MONTHLY BILLS + INVOICES (auto via service)
# ===========================================================
print("\n[6/8] Monthly Bills + Invoices...")
seen_bill_keys = set()
for c, t, d, status, _s in session_pairs:
    if status != 'completed':
        continue
    key = (c.pk, t.pk, date(d.year, d.month, 1))
    if key in seen_bill_keys:
        continue
    seen_bill_keys.add(key)
    BillingService.tick_session(client=c, therapy_type=t, target_date=d, actor=main_admin)

# Record partial / full payments on a third of bills
all_bills = list(MonthlyBill.objects.all())
for b in random.sample(all_bills, k=max(1, len(all_bills) // 3)):
    factor = random.choice([0.4, 0.6, 0.8, 1.0])
    amount = float(b.package_amount) * factor
    if amount > 0.01:
        BillingService.record_payment(
            bill_id=b.pk,
            amount=amount,
            mode=random.choice(['cash', 'upi', 'bank', 'cheque']),
            paid_date=b.month + timedelta(days=random.randint(5, 25)),
            actor=main_admin,
        )

# Regenerate invoices for unique (client, month)
seen_inv_keys = set()
for c, t, d, status, _s in session_pairs:
    key = (c.pk, date(d.year, d.month, 1))
    if key in seen_inv_keys:
        continue
    seen_inv_keys.add(key)
    InvoiceService.regenerate_for_client_month(client=c, target_date=d, actor=main_admin)

print(f"  -> {MonthlyBill.objects.count()} monthly bills, {Invoice.objects.count()} invoices")

# ===========================================================
# 7. SALARY SNAPSHOTS — past 4 months
# ===========================================================
print("\n[7/8] Salary computation (last 4 months)...")
for offset in range(0, 4):
    yr = TODAY.year
    mo = TODAY.month - offset
    while mo <= 0:
        mo += 12
        yr -= 1
    target = date(yr, mo, 1)
    SalaryService.compute_all(target, actor=main_admin)
print(f"  -> {MonthlySalary.objects.count()} monthly salary snapshots")

# ===========================================================
# 8. LEADS + FOLLOW-UPS
# ===========================================================
print("\n[8/8] Leads + Follow-ups...")
lead_names = [
    'Aanya Sharma', 'Krish Mehta', 'Riya Patel', 'Aarav Singh',
    'Diya Iyer', 'Vivaan Reddy', 'Aadhya Joshi', 'Kabir Nair',
    'Ishaan Kapoor', 'Saanvi Rao',
]
lead_count = 0
for nm in lead_names:
    status = random.choices(
        ['new', 'contacted', 'interested', 'converted', 'lost'],
        weights=[20, 25, 20, 20, 15],
    )[0]
    lead = Lead.objects.create(
        name=nm,
        mobile=f'9{random.randint(100000000, 999999999)}',
        email=f'{nm.split()[0].lower()}@example.com',
        source=random.choice(['referral', 'walk_in', 'social_media', 'website', 'phone']),
        status=status,
        assigned_to=random.choice(staff),
        notes='Demo lead',
        created_by=main_admin,
    )
    lead_count += 1

    # 1–2 follow-ups per lead (mix of past, today, future)
    for i in range(random.randint(1, 2)):
        when = timezone.now() + timedelta(
            days=random.choice([-7, -3, -1, 0, 2, 5, 10]),
            hours=random.randint(0, 18),
        )
        fu_status = 'pending'
        if when < timezone.now() - timedelta(days=1):
            fu_status = random.choice(['completed', 'missed'])
        FollowUp.objects.create(
            lead=lead,
            follow_up_date=when,
            status=fu_status,
            notes=f'Follow-up for {nm}',
            created_by=main_admin,
        )
print(f"  -> {lead_count} leads, {FollowUp.objects.count()} follow-ups")

# ===========================================================
# SUMMARY
# ===========================================================
print("\n========== SEED COMPLETE ==========")
print(f"  Appointments     : {Appointment.objects.count()}")
print(f"    completed      : {Appointment.objects.filter(status='completed').count()}")
print(f"    scheduled      : {Appointment.objects.filter(status='scheduled').count()}")
print(f"    cancelled      : {Appointment.objects.filter(status='cancelled').count()}")
print(f"    needs reassign : {Appointment.objects.filter(needs_reassignment=True).count()}")
print(f"  Attendance Logs  : {AttendanceLog.objects.count()}")
print(f"  Attendance Marks : {AttendanceMark.objects.count()}")
print(f"  Expenses         : {Expense.objects.count()}  ({Expense.objects.filter(status='pending').count()} pending)")
print(f"  Monthly Bills    : {MonthlyBill.objects.count()}")
print(f"  Invoices         : {Invoice.objects.count()}")
print(f"  Salary Settings  : {SalarySetting.objects.count()}")
print(f"  Salary Snapshots : {MonthlySalary.objects.count()}")
print(f"  Leads            : {Lead.objects.count()}")
print(f"  Follow-ups       : {FollowUp.objects.count()}")
