from django.db.models import Q

from clients.models import Client


class ClientServiceError(Exception):
    """Raised when a client service operation fails."""
    pass


class ClientService:
    """Service layer for Client CRUD and related queries."""

    @staticmethod
    def get_all_clients():
        """Return all non-deleted clients."""
        return Client.active_objects.all()

    @staticmethod
    def search_clients(query):
        """Search clients by name, mobile, or email."""
        return Client.active_objects.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(mobile_number__icontains=query)
            | Q(email__icontains=query)
        )

    @staticmethod
    def get_client(client_id):
        """Return a single client by primary key, or raise ClientServiceError."""
        try:
            return Client.active_objects.get(pk=client_id)
        except Client.DoesNotExist:
            raise ClientServiceError("Client not found.")

    @staticmethod
    def create_client(data, created_by=None):
        """Create and return a new Client instance."""
        client = Client(**data)
        if created_by:
            client.created_by = created_by
        client.full_clean()
        client.save()
        return client

    @staticmethod
    def update_client(client_id, data, updated_by=None):
        """Update an existing client with the provided data dict."""
        client = ClientService.get_client(client_id)
        for field, value in data.items():
            setattr(client, field, value)
        if updated_by:
            client.updated_by = updated_by
        client.full_clean()
        client.save()
        return client

    @staticmethod
    def delete_client(client_id, deleted_by=None):
        """Soft-delete a client."""
        client = ClientService.get_client(client_id)
        if deleted_by:
            client.updated_by = deleted_by
        client.soft_delete()
        return client

    @staticmethod
    def get_session_count(client_id):
        """Return the total number of completed appointments for a client."""
        from appointments.models import Appointment
        return Appointment.active_objects.filter(
            client_id=client_id,
            status=Appointment.Status.COMPLETED,
        ).count()

