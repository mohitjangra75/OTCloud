from django.db import transaction
from django.utils import timezone

from clients.models import Client
from lms.models import Lead, FollowUp


class LeadService:
    """Service layer for lead management operations."""

    @staticmethod
    @transaction.atomic
    def create_lead(data, created_by=None):
        """Create a new lead from a dictionary of field values."""
        lead = Lead(
            name=data['name'],
            mobile=data['mobile'],
            email=data.get('email', ''),
            source=data.get('source', Lead.Source.WALK_IN),
            status=data.get('status', Lead.Status.NEW),
            notes=data.get('notes', ''),
            created_by=created_by,
        )
        lead.save()
        return lead

    @staticmethod
    @transaction.atomic
    def convert_to_client(lead_id, converted_by=None):
        """
        Convert a lead to a client. Creates a Client record from
        the lead data and updates the lead status to CONVERTED.
        """
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        if lead.status == Lead.Status.CONVERTED:
            raise ValueError('Lead is already converted.')

        name_parts = lead.name.strip().split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        client = Client(
            first_name=first_name,
            last_name=last_name,
            mobile_number=lead.mobile,
            email=lead.email,
            created_by=converted_by,
        )
        client.save()

        lead.status = Lead.Status.CONVERTED
        lead.converted_client = client
        lead.save(update_fields=['status', 'converted_client', 'updated_at'])

        return client

    @staticmethod
    @transaction.atomic
    def add_follow_up(lead_id, follow_up_date, notes='', created_by=None):
        """Schedule a follow-up for a lead."""
        lead = Lead.objects.get(pk=lead_id)
        follow_up = FollowUp(
            lead=lead,
            follow_up_date=follow_up_date,
            notes=notes,
            created_by=created_by,
        )
        follow_up.save()
        return follow_up

    @staticmethod
    def get_pending_follow_ups(user=None):
        """Return pending follow-ups, optionally filtered by creator."""
        qs = (
            FollowUp.active_objects
            .filter(
                status='pending',
                follow_up_date__gte=timezone.now(),
            )
            .select_related('lead')
            .order_by('follow_up_date')
        )
        if user is not None:
            qs = qs.filter(created_by=user)
        return qs

    @staticmethod
    @transaction.atomic
    def update_status(lead_id, new_status, actor=None):
        """Inline status change from the leads list."""
        if new_status not in dict(Lead.Status.choices):
            raise ValueError('Invalid status.')
        lead = Lead.objects.select_for_update().get(pk=lead_id)
        lead.status = new_status
        if actor:
            lead.updated_by = actor
        lead.save(update_fields=['status', 'updated_by', 'updated_at'])
        return lead
