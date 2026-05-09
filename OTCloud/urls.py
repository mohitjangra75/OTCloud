from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from appointments import views as appointment_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('analytics.urls')),
    path('accounts/', include('accounts.urls')),
    path('attendance/', include('attendance.urls')),
    path('clients/', include('clients.urls')),
    # Top-level schedule routes (no /appointments/ prefix)
    path('schedule/', appointment_views.DailyScheduleView.as_view(), name='daily_schedule'),
    path('employee-schedule/', appointment_views.EmployeeScheduleView.as_view(), name='employee_schedule'),
    path('appointments/', include('appointments.urls')),
    path('billing/', include('billing.urls')),
    path('salary/', include('salary.urls')),
    path('lms/', include('lms.urls')),
    path('notifications/', include('notifications.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
