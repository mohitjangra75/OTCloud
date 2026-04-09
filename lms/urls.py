from django.urls import path
from lms import views

app_name = 'lms'

urlpatterns = [
    path('', views.lead_list, name='lead_list'),
    path('create/', views.lead_create, name='lead_create'),
    path('<uuid:pk>/', views.lead_detail, name='lead_detail'),
    path('<uuid:pk>/edit/', views.lead_update, name='lead_update'),
    path('<uuid:pk>/delete/', views.lead_delete, name='lead_delete'),
    path('<uuid:pk>/follow-up/', views.lead_add_follow_up, name='lead_add_follow_up'),
    path('<uuid:pk>/convert/', views.lead_convert, name='lead_convert'),
    path('follow-ups/', views.follow_up_list, name='follow_up_list'),
    path('follow-ups/<uuid:pk>/complete/', views.follow_up_mark_completed, name='follow_up_mark_completed'),
]
