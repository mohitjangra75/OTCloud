from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import ActiveManager, CoreModel


class PaymentMode(models.TextChoices):
    CASH = 'cash', 'Cash'
    UPI = 'upi', 'UPI'
    BANK = 'bank', 'Bank Transfer'
    CARD = 'card', 'Card'
    CHEQUE = 'cheque', 'Cheque'
    OTHER = 'other', 'Other'


class MonthlyBill(CoreModel):
    """One billing row per (client, therapy type, month) — matches the spreadsheet ledger."""

    class Status(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIAL = 'partial', 'Partial'
        PAID = 'paid', 'Paid'

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='monthly_bills',
    )
    therapy_type = models.ForeignKey(
        'appointments.TherapyType',
        on_delete=models.PROTECT,
        related_name='monthly_bills',
    )
    month = models.DateField(help_text='First day of the billing month')

    sessions_per_week = models.PositiveIntegerField(default=0)
    total_sessions = models.PositiveIntegerField(default=0)

    package_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    carry_forward = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Carried from previous month dues',
    )

    payment_mode = models.CharField(
        max_length=15, choices=PaymentMode.choices, blank=True,
    )
    paid_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.UNPAID,
    )
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-month', 'client__first_name']
        unique_together = ('client', 'therapy_type', 'month')

    def __str__(self):
        return f"{self.client} - {self.therapy_type} - {self.month:%b %Y}"

    @property
    def dues_current_month(self):
        bill = (self.package_amount or Decimal('0')) - (self.paid_amount or Decimal('0'))
        return bill if bill > 0 else Decimal('0')

    @property
    def total_due(self):
        return self.dues_current_month + (self.carry_forward or Decimal('0'))

    def recompute_status(self):
        target = (self.package_amount or Decimal('0')) + (self.carry_forward or Decimal('0'))
        paid = self.paid_amount or Decimal('0')
        if paid <= 0:
            self.status = self.Status.UNPAID
        elif paid >= target:
            self.status = self.Status.PAID
        else:
            self.status = self.Status.PARTIAL


class Invoice(CoreModel):
    """Per-client per-month invoice snapshot, auto-regenerated when billing changes."""

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    month = models.DateField(help_text='First day of the billing month')
    invoice_number = models.CharField(max_length=30, unique=True)

    total_sessions = models.PositiveIntegerField(default=0)
    total_billed = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    carry_forward = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    last_session_count = models.PositiveIntegerField(
        default=0,
        help_text='Snapshot session count from last regeneration',
    )
    generated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-month', 'client__first_name']
        unique_together = ('client', 'month')

    def __str__(self):
        return f"{self.invoice_number} - {self.client}"


class Expense(CoreModel):
    """Org expense or staff reimbursement entry — matches the right-side ledger."""

    class Category(models.TextChoices):
        EXPENSE = 'expense', 'Org Expense'
        REIMBURSEMENT = 'reimbursement', 'Reimbursement'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REIMBURSED = 'reimbursed', 'Reimbursed'
        REJECTED = 'rejected', 'Rejected'

    date = models.DateField()
    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.EXPENSE,
    )
    item = models.CharField(max_length=255)
    remarks = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(
        max_length=15, choices=PaymentMode.choices, blank=True,
    )
    paid_to = models.CharField(
        max_length=120, blank=True,
        help_text='Vendor name (for org expenses)',
    )
    paid_to_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reimbursements_received',
        limit_choices_to={'role__in': ['staff', 'admin']},
        help_text='Employee being reimbursed (if reimbursement)',
    )
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses_paid',
    )
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.APPROVED,
    )

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.date} - {self.item} ({self.amount})"
