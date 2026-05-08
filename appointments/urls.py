from django.urls import path

from appointments import views

app_name = 'appointments'

urlpatterns = [
    # Default landing — day-wise schedule grid (defaults to tomorrow)
    path('', views.DailyScheduleView.as_view(), name='daily_schedule'),
    path('employee-schedule/', views.EmployeeScheduleView.as_view(), name='employee_schedule'),
    path('schedule/quick-add/', views.ScheduleQuickAddView.as_view(), name='schedule_quick_add'),
    path('schedule/copy-day/', views.ScheduleCopyDayView.as_view(), name='schedule_copy_day'),

    # List view (history / filtering)
    path('list/', views.AppointmentListView.as_view(), name='appointment_list'),

    path('create/', views.AppointmentCreateView.as_view(), name='appointment_create'),
    path('<int:pk>/', views.AppointmentDetailView.as_view(), name='appointment_detail'),
    path('<int:pk>/edit/', views.AppointmentUpdateView.as_view(), name='appointment_update'),
    path('<int:pk>/delete/', views.AppointmentDeleteView.as_view(), name='appointment_delete'),
    path('<int:pk>/reschedule/', views.AppointmentRescheduleView.as_view(), name='appointment_reschedule'),
    path('<int:pk>/cancel/', views.AppointmentCancelView.as_view(), name='appointment_cancel'),
    path('<int:pk>/complete/', views.AppointmentCompleteView.as_view(), name='appointment_complete'),
    path('<int:pk>/reassign/', views.AppointmentReassignView.as_view(), name='appointment_reassign'),
    path('<int:pk>/quick-reassign/', views.AppointmentQuickReassignView.as_view(), name='appointment_quick_reassign'),
    path('<int:pk>/mark-absent/', views.AppointmentMarkAbsentView.as_view(), name='appointment_mark_absent'),
]
