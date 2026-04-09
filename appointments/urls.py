from django.urls import path

from appointments import views

app_name = 'appointments'

urlpatterns = [
    path('', views.AppointmentListView.as_view(), name='appointment_list'),
    path('create/', views.AppointmentCreateView.as_view(), name='appointment_create'),
    path('<uuid:pk>/', views.AppointmentDetailView.as_view(), name='appointment_detail'),
    path('<uuid:pk>/edit/', views.AppointmentUpdateView.as_view(), name='appointment_update'),
    path('<uuid:pk>/delete/', views.AppointmentDeleteView.as_view(), name='appointment_delete'),
    path('<uuid:pk>/reschedule/', views.AppointmentRescheduleView.as_view(), name='appointment_reschedule'),
    path('<uuid:pk>/cancel/', views.AppointmentCancelView.as_view(), name='appointment_cancel'),
    path('<uuid:pk>/complete/', views.AppointmentCompleteView.as_view(), name='appointment_complete'),
]
