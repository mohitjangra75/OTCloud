from notifications.services import NotificationService


def unread_notifications_count(request):
    """Add unread notification count to template context."""
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': NotificationService.get_unread_count(request.user),
        }
    return {'unread_notifications_count': 0}
