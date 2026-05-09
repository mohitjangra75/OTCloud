from django.db import models
from django.conf import settings
from core.models import CoreModel, ActiveManager


class Client(CoreModel):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'
        OTHER = 'other', 'Other'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_profile',
        null=True, blank=True,
    )
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50, blank=True)
    mobile_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    address = models.TextField(blank=True)
    medical_history = models.TextField(blank=True)
    assigned_therapist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_clients',
        limit_choices_to={'role__in': ['staff', 'admin']},
    )

    # Schedule preference — comma-separated weekday codes (mon,tue,wed,thu,fri,sat,sun)
    preferred_days = models.CharField(
        max_length=40, blank=True,
        help_text='Comma-separated weekday codes the client prefers, e.g. "mon,wed,fri"',
    )
    preferred_time_start = models.TimeField(null=True, blank=True)
    preferred_time_end = models.TimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    DAY_LABELS = {
        'mon': 'Mon', 'tue': 'Tue', 'wed': 'Wed', 'thu': 'Thu',
        'fri': 'Fri', 'sat': 'Sat', 'sun': 'Sun',
    }

    @property
    def preferred_days_list(self):
        if not self.preferred_days:
            return []
        codes = [d.strip().lower() for d in self.preferred_days.split(',') if d.strip()]
        return [self.DAY_LABELS[c] for c in codes if c in self.DAY_LABELS]

    @property
    def preferred_schedule_label(self):
        days = self.preferred_days_list
        if not days and not (self.preferred_time_start or self.preferred_time_end):
            return ''
        parts = []
        if days:
            parts.append(', '.join(days))
        if self.preferred_time_start and self.preferred_time_end:
            parts.append(f"{self.preferred_time_start.strftime('%I:%M %p').lstrip('0')} – {self.preferred_time_end.strftime('%I:%M %p').lstrip('0')}")
        elif self.preferred_time_start:
            parts.append(f"from {self.preferred_time_start.strftime('%I:%M %p').lstrip('0')}")
        elif self.preferred_time_end:
            parts.append(f"until {self.preferred_time_end.strftime('%I:%M %p').lstrip('0')}")
        return ' • '.join(parts)
