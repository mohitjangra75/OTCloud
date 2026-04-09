from django.db import models
from django.conf import settings
from core.models import CoreModel, ActiveManager, TimeStampModel


class TherapyType(TimeStampModel):
    """Types of therapy sessions with duration and pricing."""
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    duration = models.IntegerField(
        help_text='Session duration in minutes',
    )
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Price for this session',
    )

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['name', 'duration']

    def __str__(self):
        return f"{self.name} ({self.duration} min)"


class Appointment(CoreModel):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'
        RESCHEDULED = 'rescheduled', 'Rescheduled'

    client = models.ForeignKey(
        'clients.Client',
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_appointments',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )
    therapy_type = models.ForeignKey(
        TherapyType,
        on_delete=models.PROTECT,
        related_name='appointments',
        null=True,
        blank=True,
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    session_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=0,
        help_text='Auto-calculated from therapy type',
    )
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-date', '-start_time']

    def __str__(self):
        therapy = f" - {self.therapy_type.name}" if self.therapy_type else ""
        return f"{self.client} - {self.date}{therapy}"

    def calculate_price(self):
        """Calculate session price from therapy type."""
        if self.therapy_type:
            self.session_price = self.therapy_type.price
        return self.session_price

    def save(self, *args, **kwargs):
        if self.therapy_type and not self.session_price:
            self.calculate_price()
        super().save(*args, **kwargs)
