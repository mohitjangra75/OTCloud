from django.db import models
from django.conf import settings
from core.models import CoreModel, ActiveManager


class AttendanceLog(CoreModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendance_logs',
    )
    check_in_time = models.DateTimeField()
    check_out_time = models.DateTimeField(null=True, blank=True)
    date = models.DateField()
    duration = models.DurationField(null=True, blank=True)
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-date', '-check_in_time']

    def __str__(self):
        return f"{self.user} - {self.date} ({self.check_in_time.strftime('%H:%M')})"

    def calculate_duration(self):
        if self.check_in_time and self.check_out_time:
            self.duration = self.check_out_time - self.check_in_time
        return self.duration

    def save(self, *args, **kwargs):
        self.calculate_duration()
        super().save(*args, **kwargs)
