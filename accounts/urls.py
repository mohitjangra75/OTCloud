from django.urls import path

from accounts import views

app_name = 'accounts'

urlpatterns = [
    # Registration
    path('register/', views.register_view, name='register'),
    path('register/verify-otp/', views.register_verify_otp_view, name='register_verify_otp'),
    path('register/complete/', views.register_complete_view, name='register_complete'),

    # Login / Logout
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Profile
    path('profile/', views.profile_view, name='profile'),

    # Employee Management
    path('employees/', views.employee_list_view, name='employee_list'),
    path('employees/create/', views.create_employee_view, name='employee_create'),
    path('employees/<uuid:pk>/', views.employee_detail_view, name='employee_detail'),

    # Forgot / Reset Password
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('forgot-password/verify-otp/', views.reset_verify_otp_view, name='reset_verify_otp'),
    path('forgot-password/reset/', views.reset_password_view, name='reset_password'),
]
