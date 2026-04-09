from notifications.models import Notification


class NotificationService:
    """Service layer for notification operations."""

    @staticmethod
    def create(user, title, message, type=Notification.Type.SYSTEM, action_url=''):
        """Create a new notification for a user."""
        notification = Notification(
            user=user,
            title=title,
            message=message,
            type=type,
            action_url=action_url,
        )
        notification.save()
        return notification

    @staticmethod
    def mark_read(notification_id):
        """Mark a single notification as read."""
        Notification.objects.filter(pk=notification_id).update(is_read=True)

    @staticmethod
    def mark_all_read(user):
        """Mark all notifications for a user as read."""
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)

    @staticmethod
    def get_unread(user):
        """Return unread notifications for a user."""
        return (
            Notification.active_objects
            .filter(user=user, is_read=False)
            .order_by('-created_at')
        )

    @staticmethod
    def get_unread_count(user):
        """Return count of unread notifications for a user."""
        return (
            Notification.active_objects
            .filter(user=user, is_read=False)
            .count()
        )
