from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from billing.models import Expense, Invoice, MonthlyBill


class BillingServiceError(Exception):
    """Raised when a billing operation fails."""


def first_of_month(d):
    return date(d.year, d.month, 1)


def previous_month(d):
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def next_month(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


class BillingService:
    """Monthly per-client billing operations."""

    @staticmethod
    @transaction.atomic
    def create_or_update_bill(
        client, therapy_type, month,
        sessions_per_week=0, total_sessions=0,
        package_amount=0, paid_amount=0, carry_forward=None,
        payment_mode='', paid_date=None, notes='',
        actor=None,
    ):
        month = first_of_month(month)
        bill, _created = MonthlyBill.objects.get_or_create(
            client=client, therapy_type=therapy_type, month=month,
            defaults={'created_by': actor},
        )
        if carry_forward is None:
            carry_forward = BillingService.compute_carry_forward(client, therapy_type, month)

        bill.sessions_per_week = sessions_per_week or 0
        bill.total_sessions = total_sessions or 0
        bill.package_amount = Decimal(str(package_amount or 0))
        bill.paid_amount = Decimal(str(paid_amount or 0))
        bill.carry_forward = Decimal(str(carry_forward or 0))
        bill.payment_mode = payment_mode or ''
        bill.paid_date = paid_date
        bill.notes = notes or ''
        bill.is_deleted = False
        if actor:
            bill.updated_by = actor
        bill.recompute_status()
        bill.save()
        InvoiceService.regenerate_for_client_month(client, month, actor=actor)
        return bill

    @staticmethod
    @transaction.atomic
    def record_payment(bill_id, amount, mode='', paid_date=None, actor=None):
        amt = Decimal(str(amount or 0))
        if amt <= 0:
            raise BillingServiceError('Payment amount must be greater than zero.')
        bill = MonthlyBill.objects.select_for_update().get(pk=bill_id)
        bill.paid_amount = (bill.paid_amount or Decimal('0')) + amt
        if mode:
            bill.payment_mode = mode
        bill.paid_date = paid_date or date.today()
        if actor:
            bill.updated_by = actor
        bill.recompute_status()
        bill.save()
        InvoiceService.regenerate_for_client_month(bill.client, bill.month, actor=actor)
        return bill

    @staticmethod
    def compute_carry_forward(client, therapy_type, month):
        """Sum of (package + carry - paid) from prior months for this client+therapy."""
        prior = MonthlyBill.active_objects.filter(
            client=client, therapy_type=therapy_type, month__lt=first_of_month(month),
        )
        total_billed = Decimal('0')
        total_paid = Decimal('0')
        for b in prior:
            total_billed += (b.package_amount or Decimal('0')) + (b.carry_forward or Decimal('0'))
            total_paid += (b.paid_amount or Decimal('0'))
        diff = total_billed - total_paid
        return diff if diff > 0 else Decimal('0')

    @staticmethod
    def get_month_bills(month, client_id=None):
        month = first_of_month(month)
        qs = (MonthlyBill.active_objects
              .filter(month=month)
              .select_related('client', 'therapy_type')
              .order_by('client__first_name', 'client__last_name', 'therapy_type__name'))
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    @staticmethod
    def month_summary(month):
        qs = MonthlyBill.active_objects.filter(month=first_of_month(month))
        agg = qs.aggregate(
            billed=Sum('package_amount'),
            paid=Sum('paid_amount'),
            carry=Sum('carry_forward'),
        )
        billed = agg['billed'] or Decimal('0')
        paid = agg['paid'] or Decimal('0')
        carry = agg['carry'] or Decimal('0')
        outstanding = (billed + carry) - paid
        return {
            'rows': qs.count(),
            'billed': billed,
            'paid': paid,
            'carry_forward': carry,
            'outstanding': outstanding if outstanding > 0 else Decimal('0'),
        }

    @staticmethod
    @transaction.atomic
    def tick_session(client, therapy_type, target_date, actor=None):
        """Called when an appointment is completed.

        Find or create the MonthlyBill row for (client, therapy_type, month-of(target_date))
        and recompute total_sessions from completed Appointment count. Auto-fill
        sessions_per_week from completed-in-first-week count if blank.
        """
        from appointments.models import Appointment

        month = first_of_month(target_date)
        month_end = next_month(month)

        bill, created = MonthlyBill.objects.get_or_create(
            client=client, therapy_type=therapy_type, month=month,
            defaults={'created_by': actor},
        )

        completed_qs = Appointment.active_objects.filter(
            client=client, therapy_type=therapy_type,
            status=Appointment.Status.COMPLETED,
            date__gte=month, date__lt=month_end,
        )
        bill.total_sessions = completed_qs.count()

        # Auto-fill sessions_per_week if it's still 0 — count first calendar week's completed
        if not bill.sessions_per_week:
            week_end = month + timedelta(days=7)
            week_count = completed_qs.filter(date__gte=month, date__lt=week_end).count()
            if week_count:
                bill.sessions_per_week = week_count

        # Auto-fill carry forward if newly created
        if created:
            bill.carry_forward = BillingService.compute_carry_forward(client, therapy_type, month)
            # Auto-fill package amount: total_sessions × therapy_type.price (admin can edit)
            try:
                price = therapy_type.price or 0
                if bill.total_sessions and price:
                    bill.package_amount = Decimal(str(price)) * bill.total_sessions
            except AttributeError:
                pass

        if actor:
            bill.updated_by = actor
        bill.recompute_status()
        bill.is_deleted = False
        bill.save()
        return bill




class InvoiceService:
    """Per-(client, month) invoice snapshot regeneration."""

    @staticmethod
    def _generate_number(client, month):
        return f"INV-{client.pk:04d}-{month.strftime('%Y%m')}"

    @staticmethod
    @transaction.atomic
    def regenerate_for_client_month(client, target_date, actor=None):
        """Aggregate MonthlyBill rows for (client, month) and refresh the invoice.

        Skips creation if there are no active billing rows (avoids empty invoices).
        If an invoice already exists, totals are updated even when bills are zero
        (so the invoice reflects current state).
        """
        month = first_of_month(target_date)
        bills = MonthlyBill.active_objects.filter(client=client, month=month)

        agg = bills.aggregate(
            sessions=Sum('total_sessions'),
            billed=Sum('package_amount'),
            paid=Sum('paid_amount'),
            carry=Sum('carry_forward'),
        )
        sessions = agg['sessions'] or 0
        billed = agg['billed'] or Decimal('0')
        paid = agg['paid'] or Decimal('0')
        carry = agg['carry'] or Decimal('0')
        balance = billed + carry - paid

        existing = Invoice.objects.filter(client=client, month=month).first()
        if existing is None and not bills.exists():
            # No bills and no prior invoice — nothing to do.
            return None

        invoice, _created = Invoice.objects.get_or_create(
            client=client, month=month,
            defaults={
                'invoice_number': InvoiceService._generate_number(client, month),
                'created_by': actor,
            },
        )
        invoice.total_sessions = sessions
        invoice.total_billed = billed
        invoice.total_paid = paid
        invoice.carry_forward = carry
        invoice.balance_due = balance if balance > 0 else Decimal('0')
        invoice.last_session_count = sessions
        invoice.is_deleted = False
        if actor:
            invoice.updated_by = actor
        invoice.save()
        return invoice

    @staticmethod
    def get_invoices(client_id=None, month=None):
        qs = (Invoice.active_objects
              .select_related('client')
              .order_by('-month', 'client__first_name'))
        if client_id:
            qs = qs.filter(client_id=client_id)
        if month:
            qs = qs.filter(month=first_of_month(month))
        return qs

    @staticmethod
    def get_invoice_with_lines(invoice):
        """Return an invoice plus its underlying MonthlyBill rows for display."""
        lines = (MonthlyBill.active_objects
                 .filter(client=invoice.client, month=invoice.month)
                 .select_related('therapy_type')
                 .order_by('therapy_type__name'))
        return invoice, list(lines)


class PnLService:
    """Profit-and-loss aggregation derived from completed appointments + expenses."""

    @staticmethod
    def _income_for_range(start, end_exclusive):
        """Return (total_income, session_count) for completed appointments
        in [start, end_exclusive). Trial / walk-in sessions (no linked Client)
        are always free — excluded from both totals and session count."""
        from appointments.models import Appointment
        qs = Appointment.active_objects.filter(
            status=Appointment.Status.COMPLETED,
            client__isnull=False,  # exclude trial / walk-in sessions
            date__gte=start, date__lt=end_exclusive,
        )
        total = qs.aggregate(t=Sum('session_price'))['t'] or Decimal('0')
        count = qs.count()
        return total, count

    @staticmethod
    def _expense_for_range(start, end_exclusive):
        # Org expenses + staff reimbursements
        ex_total = Expense.active_objects.filter(
            date__gte=start, date__lt=end_exclusive,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        # Plus computed salaries for months in range (MonthlySalary.month is 1st-of-month)
        try:
            from salary.models import MonthlySalary
            sal_total = MonthlySalary.active_objects.filter(
                month__gte=start, month__lt=end_exclusive,
            ).aggregate(t=Sum('in_hand_salary'))['t'] or Decimal('0')
        except Exception:
            sal_total = Decimal('0')
        return ex_total + sal_total

    @staticmethod
    def month(target_date):
        start = first_of_month(target_date)
        end = next_month(start)
        income, session_count = PnLService._income_for_range(start, end)
        expenses = PnLService._expense_for_range(start, end)
        return {
            'period': start.strftime('%B %Y'),
            'start': start, 'end': end,
            'session_count': session_count,
            'total_income': income,
            'total_expenses': expenses,
            'profit_loss': income - expenses,
        }

    @staticmethod
    def year(year):
        year_start = date(year, 1, 1)
        year_end = date(year + 1, 1, 1)
        months = []
        for m in range(1, 13):
            months.append(PnLService.month(date(year, m, 1)))
        income = sum((m['total_income'] for m in months), Decimal('0'))
        expenses = sum((m['total_expenses'] for m in months), Decimal('0'))
        sessions = sum(m['session_count'] for m in months)
        return {
            'year': year,
            'start': year_start, 'end': year_end,
            'months': months,
            'session_count': sessions,
            'total_income': income,
            'total_expenses': expenses,
            'profit_loss': income - expenses,
        }


class ExpenseService:
    """Org expense + reimbursement operations."""

    @staticmethod
    @transaction.atomic
    def create_expense(
        date_, item, amount,
        category=Expense.Category.EXPENSE,
        remarks='', payment_mode='',
        paid_to='', paid_to_employee=None, paid_by=None,
        status=None, actor=None,
    ):
        if not status:
            status = (Expense.Status.PENDING
                      if category == Expense.Category.REIMBURSEMENT
                      else Expense.Status.APPROVED)
        return Expense.objects.create(
            date=date_,
            item=item,
            amount=Decimal(str(amount or 0)),
            category=category,
            remarks=remarks or '',
            payment_mode=payment_mode or '',
            paid_to=paid_to or '',
            paid_to_employee=paid_to_employee,
            paid_by=paid_by,
            status=status,
            created_by=actor,
        )

    @staticmethod
    @transaction.atomic
    def update_expense(expense_id, actor=None, **fields):
        exp = Expense.objects.get(pk=expense_id)
        for key, val in fields.items():
            if hasattr(exp, key) and val is not None:
                setattr(exp, key, val)
        if actor:
            exp.updated_by = actor
        exp.save()
        return exp

    @staticmethod
    def get_month_expenses(month, category=None):
        first = first_of_month(month)
        last = next_month(first)
        qs = (Expense.active_objects
              .filter(date__gte=first, date__lt=last)
              .select_related('paid_to_employee', 'paid_by')
              .order_by('date', 'id'))
        if category:
            qs = qs.filter(category=category)
        return qs

    @staticmethod
    def month_summary(month):
        first = first_of_month(month)
        last = next_month(first)
        qs = Expense.active_objects.filter(date__gte=first, date__lt=last)

        org = qs.filter(category=Expense.Category.EXPENSE).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        reimb = qs.filter(category=Expense.Category.REIMBURSEMENT).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        pending = qs.filter(
            category=Expense.Category.REIMBURSEMENT,
            status=Expense.Status.PENDING,
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        return {
            'rows': qs.count(),
            'org_total': org,
            'reimb_total': reimb,
            'reimb_pending': pending,
            'grand_total': org + reimb,
        }
