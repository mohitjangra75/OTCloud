from django.db import models
from django.conf import settings
from core.models import CoreModel, ActiveManager


class Lead(CoreModel):
    class Source(models.TextChoices):
        WALK_IN = 'walk_in', 'Walk-in'
        REFERRAL = 'referral', 'Referral'
        WEBSITE = 'website', 'Website'
        SOCIAL_MEDIA = 'social_media', 'Social Media'
        PHONE = 'phone', 'Phone'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        INTERESTED = 'interested', 'Interested'
        CONVERTED = 'converted', 'Converted'
        LOST = 'lost', 'Lost'

    name = models.CharField(max_length=100)
    mobile = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WALK_IN)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_leads',
    )
    notes = models.TextField(blank=True)
    converted_client = models.ForeignKey(
        'clients.Client',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lead_source',
    )

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.mobile})"


class FollowUp(CoreModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='follow_ups')
    follow_up_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('missed', 'Missed'),
    ], default='pending')
    notes = models.TextField(blank=True)

    objects = models.Manager()
    active_objects = ActiveManager()

    class Meta:
        ordering = ['-follow_up_date']

    def __str__(self):
        return f"Follow-up: {self.lead.name} - {self.follow_up_date}"
