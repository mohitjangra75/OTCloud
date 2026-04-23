from django.urls import path

from attendance.views import (
    AttendanceDashboardView,
    AttendanceHistoryView,
    AttendanceMarkView,
    AttendanceUnmarkView,
    CheckInView,
    CheckOutView,
    MyAttendanceView,
    TeamDayView,
    TeamMonthView,
    live_timer_api,
)

app_name = 'attendance'

urlpatterns = [
    path('', AttendanceDashboardView.as_view(), name='dashboard'),
    path('me/', MyAttendanceView.as_view(), name='my_attendance'),
    path('check-in/', CheckInView.as_view(), name='check_in'),
    path('check-out/', CheckOutView.as_view(), name='check_out'),
    path('history/', AttendanceHistoryView.as_view(), name='history'),

    # Admin-only team views
    path('team/', TeamDayView.as_view(), name='team_day'),
    path('team/month/', TeamMonthView.as_view(), name='team_month'),
    path('mark/', AttendanceMarkView.as_view(), name='mark'),
    path('unmark/', AttendanceUnmarkView.as_view(), name='unmark'),

    path('api/timer/', live_timer_api, name='live_timer'),
]
