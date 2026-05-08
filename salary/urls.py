from django.urls import path

from salary import views

app_name = 'salary'

urlpatterns = [
    path('', views.salary_list, name='salary_list'),
    path('me/', views.my_salary, name='my_salary'),
    path('settings/<int:employee_id>/', views.settings_edit, name='settings_edit'),
]
