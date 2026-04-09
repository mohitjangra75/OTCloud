from django.urls import path

from appointments import views

app_name = 'appointments'

urlpatterns = [
    path('', views.AppointmentListView.as_view(), name='appointment_list'),
    path('create/', views.AppointmentCreateView.as_view(), name='appointment_create'),
    path('<int:pk>/', views.AppointmentDetailView.as_view(), name='appointment_detail'),
    path('<int:pk>/edit/', views.AppointmentUpdateView.as_view(), name='appointment_update'),
    path('<int:pk>/delete/', views.AppointmentDeleteView.as_view(), name='appointment_delete'),
    path('<int:pk>/reschedule/', views.AppointmentRescheduleView.as_view(), name='appointment_reschedule'),
    path('<int:pk>/cancel/', views.AppointmentCancelView.as_view(), name='appointment_cancel'),
    path('<int:pk>/complete/', views.AppointmentCompleteView.as_view(), name='appointment_complete'),
    path('<int:pk>/reassign/', views.AppointmentReassignView.as_view(), name='appointment_reassign'),
]
