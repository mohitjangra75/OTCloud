from django.urls import path

from attendance.views import (
    AttendanceDashboardView,
    AttendanceHistoryView,
    CheckInView,
    CheckOutView,
    live_timer_api,
)

app_name = 'attendance'

urlpatterns = [
    path('', AttendanceDashboardView.as_view(), name='dashboard'),
    path('check-in/', CheckInView.as_view(), name='check_in'),
    path('check-out/', CheckOutView.as_view(), name='check_out'),
    path('history/', AttendanceHistoryView.as_view(), name='history'),
    path('api/timer/', live_timer_api, name='live_timer'),
]
