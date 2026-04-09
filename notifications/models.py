from django.db import models
from django.conf import settings
from core.models import CoreModel, ActiveManager


class Notification(CoreModel):
    class Type(models.TextChoices):
        ATTENDANCE = 'attendance', 'Attendance'
        APPOINTMENT = 'appointment', 'Appointment'
        BILLING = 'billing', 'Billing'
        LMS = 'lms', 'Lead Management'
        SYSTEM = 'system', 'System'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    type = models.CharField(max_length=15, choices=Type.choices, default=Type.SYSTEM)
    is_read = models.BooleanField(default=False)
    action_url = models.CharField(max_length=255, blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} → {self.user}"
