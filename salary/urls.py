from django.urls import path

from salary import views

app_name = 'salary'

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
    path('me/', views.my_salary, name='my_salary'),
    path('settings/<int:employee_id>/', views.settings_edit, name='settings_edit'),

    # Performance ratings
    path('rate/', views.rate_my_therapist, name='rate_my_therapist'),
    path('ratings/', views.ratings_list, name='ratings_list'),
]
