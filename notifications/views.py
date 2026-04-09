from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from notifications.models import Notification
from notifications.services import NotificationService


@login_required
def notification_list(request):
    queryset = (
        Notification.active_objects
        .filter(user=request.user)
        .order_by('-created_at')
    )

    paginator = Paginator(queryset, 20)
    page = paginator.get_page(request.GET.get('page'))

    has_unread = queryset.filter(is_read=False).exists()

    return render(request, 'notifications/notification_list.html', {
        'page_obj': page,
        'has_unread': has_unread,
    })


@login_required
def notification_mark_read(request, pk):
    if request.method == 'POST':
        notification = (
            Notification.active_objects
            .filter(pk=pk, user=request.user)
            .first()
        )
        if notification:
            NotificationService.mark_read(notification.pk)
            if notification.action_url:
                return redirect(notification.action_url)
        messages.success(request, 'Notification marked as read.')
    return redirect('notifications:notification_list')


@login_required
def notification_mark_all_read(request):
    if request.method == 'POST':
        NotificationService.mark_all_read(request.user)
        messages.success(request, 'All notifications marked as read.')
    return redirect('notifications:notification_list')
