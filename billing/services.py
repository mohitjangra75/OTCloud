from datetime import date

from django.db import transaction
from django.db.models import Max

from billing.models import Invoice, InvoiceItem


class BillingService:
    """Service layer for billing operations."""

    @staticmethod
    def _generate_invoice_number():
        """Generate an invoice number in the format INV-YYYYMMDD-NNN."""
        today = date.today()
        prefix = f"INV-{today.strftime('%Y%m%d')}-"
        last_invoice = (
            Invoice.objects
            .filter(invoice_number__startswith=prefix)
            .aggregate(max_num=Max('invoice_number'))
        )
        last_number = last_invoice['max_num']
        if last_number:
            sequence = int(last_number.split('-')[-1]) + 1
        else:
            sequence = 1
        return f"{prefix}{sequence:03d}"

    @staticmethod
    @transaction.atomic
    def create_invoice(client, due_date=None, notes='', created_by=None):
        """Create a new draft invoice for a client."""
        invoice = Invoice(
            client=client,
            invoice_number=BillingService._generate_invoice_number(),
            status=Invoice.Status.DRAFT,
            due_date=due_date,
            notes=notes,
            created_by=created_by,
        )
        invoice.save()
        return invoice

    @staticmethod
    @transaction.atomic
    def add_item(invoice, date, description, amount, appointment=None, created_by=None):
        """Add a line item to an invoice and recalculate the total."""
        item = InvoiceItem(
            invoice=invoice,
            date=date,
            description=description,
            amount=amount,
            appointment=appointment,
            created_by=created_by,
        )
        item.save()
        invoice.recalculate_total()
        return item

    @staticmethod
    @transaction.atomic
    def mark_paid(invoice_id, amount):
        """Record a payment against an invoice."""
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
        invoice.paid_amount += amount
        if invoice.paid_amount >= invoice.total_amount:
            invoice.status = Invoice.Status.PAID
        update_fields = ['paid_amount', 'status', 'updated_at']
        invoice.save(update_fields=update_fields)
        return invoice

    @staticmethod
    def get_client_invoices(client_id):
        """Return all non-deleted invoices for a client."""
        return (
            Invoice.active_objects
            .filter(client_id=client_id)
            .select_related('client')
            .prefetch_related('items')
        )

    @staticmethod
    @transaction.atomic
    def append_daily_session(client, appointment, description=None, amount=0, created_by=None):
        """
        Add a session item to an existing draft invoice for the client,
        or create a new draft invoice if none exists.
        """
        draft_invoice = (
            Invoice.active_objects
            .filter(client=client, status=Invoice.Status.DRAFT)
            .order_by('-created_at')
            .first()
        )
        if draft_invoice is None:
            draft_invoice = BillingService.create_invoice(
                client=client,
                created_by=created_by,
            )

        desc = description or f"Session on {appointment.date}"
        return BillingService.add_item(
            invoice=draft_invoice,
            date=appointment.date,
            description=desc,
            amount=amount,
            appointment=appointment,
            created_by=created_by,
        )
