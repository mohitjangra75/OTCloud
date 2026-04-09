from django.db import models
from core.models import CoreModel, ActiveManager


class Invoice(CoreModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        PAID = 'paid', 'Paid'
        OVERDUE = 'overdue', 'Overdue'

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='invoices',
    )
    invoice_number = models.CharField(max_length=20, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"INV-{self.invoice_number} - {self.client}"

    @property
    def balance_due(self):
        return self.total_amount - self.paid_amount

    def recalculate_total(self):
        self.total_amount = self.items.aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        self.save(update_fields=['total_amount', 'updated_at'])


class InvoiceItem(CoreModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items',
    )
    date = models.DateField()
    description = models.CharField(max_length=255)
    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.description} - {self.amount}"
