from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import admin_required, staff_required
from accounts.forms import (
    EmployeeCreateForm,
    ForgotPasswordForm,
    LoginForm,
    OTPVerificationForm,
    ProfileForm,
    RegistrationCompleteForm,
    RegistrationForm,
    ResetPasswordForm,
)
from accounts.services import AuthService, OTPService

User = get_user_model()


# ---------------------------------------------------------------------------
# Registration (3-step: mobile -> OTP -> profile + password)
# ---------------------------------------------------------------------------

def register_view(request):
    """Step 1: Collect mobile number and send OTP."""
    if request.user.is_authenticated:
        return redirect('/')

    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mobile = form.cleaned_data['mobile_number']

        if not OTPService.rate_limit_check(mobile, 'register'):
            messages.error(request, 'Too many OTP requests. Please try again later.')
            return render(request, 'accounts/register.html', {'form': form})

        OTPService.generate_otp(mobile, 'register')
        request.session['registration_mobile'] = mobile
        request.session['registration_email'] = form.cleaned_data.get('email', '')
        request.session['registration_first_name'] = form.cleaned_data.get('first_name', '')
        request.session['registration_last_name'] = form.cleaned_data.get('last_name', '')
        request.session['registration_role'] = form.cleaned_data.get('role', 'client')
        messages.success(request, 'OTP sent to your mobile number.')
        return redirect('accounts:register_verify_otp')

    return render(request, 'accounts/register.html', {'form': form})


def register_verify_otp_view(request):
    """Step 2: Verify OTP for registration."""
    if request.user.is_authenticated:
        return redirect('/')

    mobile = request.session.get('registration_mobile')
    if not mobile:
        messages.error(request, 'Please start the registration process again.')
        return redirect('accounts:register')

    form = OTPVerificationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['otp']
        if OTPService.verify_otp(mobile, code, 'register'):
            request.session['registration_otp_verified'] = True
            messages.success(request, 'Mobile number verified.')
            return redirect('accounts:register_complete')
        else:
            messages.error(request, 'Invalid or expired OTP. Please try again.')

    return render(request, 'accounts/register_verify_otp.html', {
        'form': form,
        'mobile_number': mobile,
    })


def register_complete_view(request):
    """Step 3: Set password and profile info after OTP verification."""
    if request.user.is_authenticated:
        return redirect('/')

    mobile = request.session.get('registration_mobile')
    otp_verified = request.session.get('registration_otp_verified')
    if not mobile or not otp_verified:
        messages.error(request, 'Please complete mobile verification first.')
        return redirect('accounts:register')

    first_name = request.session.get('registration_first_name', '')
    last_name = request.session.get('registration_last_name', '')
    email = request.session.get('registration_email', '')
    role = request.session.get('registration_role', 'client')

    form = RegistrationCompleteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = AuthService.create_user(
            mobile_number=mobile,
            password=form.cleaned_data['password1'],
            first_name=first_name,
            last_name=last_name,
            email=email,
            role=role,
        )

        # Clean up session
        request.session.pop('registration_mobile', None)
        request.session.pop('registration_otp_verified', None)
        request.session.pop('registration_first_name', None)
        request.session.pop('registration_last_name', None)
        request.session.pop('registration_email', None)
        request.session.pop('registration_role', None)

        login(request, user)
        messages.success(request, 'Registration successful. Welcome!')
        return redirect('/')

    return render(request, 'accounts/register_complete.html', {
        'form': form,
        'mobile_number': mobile,
        'first_name': first_name,
    })


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

def login_view(request):
    """Authenticate user with mobile number and password."""
    if request.user.is_authenticated:
        return redirect('/')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mobile = form.cleaned_data['mobile_number']
        password = form.cleaned_data['password']
        user = authenticate(request, mobile_number=mobile, password=password)

        if user is None:
            messages.error(request, 'Invalid mobile number or password.')
        elif not user.is_active:
            messages.error(request, 'Your account has been deactivated. Contact support.')
        elif not user.is_verified:
            messages.error(request, 'Your account is not verified yet.')
        else:
            login(request, user)
            messages.success(request, f'Welcome back, {user.get_full_name() or user.mobile_number}!')
            next_url = request.GET.get('next', '/')
            return redirect(next_url)

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """Log the user out and redirect to login page."""
    if request.method == 'POST':
        logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('accounts:login')
    return render(request, 'accounts/logout.html')


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@login_required
def profile_view(request):
    """View and edit current user's profile."""
    form = ProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {'form': form})


# ---------------------------------------------------------------------------
# Forgot / Reset Password (3-step: mobile -> OTP -> new password)
# ---------------------------------------------------------------------------

def forgot_password_view(request):
    """Step 1: Collect mobile number for password reset."""
    if request.user.is_authenticated:
        return redirect('/')

    form = ForgotPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        mobile = form.cleaned_data['mobile_number']

        if not OTPService.rate_limit_check(mobile, 'reset'):
            messages.error(request, 'Too many OTP requests. Please try again later.')
            return render(request, 'accounts/forgot_password.html', {'form': form})

        OTPService.generate_otp(mobile, 'reset')
        request.session['reset_mobile'] = mobile
        messages.success(request, 'OTP sent to your mobile number.')
        return redirect('accounts:reset_verify_otp')

    return render(request, 'accounts/forgot_password.html', {'form': form})


def reset_verify_otp_view(request):
    """Step 2: Verify OTP for password reset."""
    if request.user.is_authenticated:
        return redirect('/')

    mobile = request.session.get('reset_mobile')
    if not mobile:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('accounts:forgot_password')

    form = OTPVerificationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['otp']
        if OTPService.verify_otp(mobile, code, 'reset'):
            request.session['reset_otp_verified'] = True
            messages.success(request, 'OTP verified. Set your new password.')
            return redirect('accounts:reset_password')
        else:
            messages.error(request, 'Invalid or expired OTP. Please try again.')

    return render(request, 'accounts/reset_verify_otp.html', {
        'form': form,
        'mobile_number': mobile,
    })


def reset_password_view(request):
    """Step 3: Set new password after OTP verification."""
    if request.user.is_authenticated:
        return redirect('/')

    mobile = request.session.get('reset_mobile')
    otp_verified = request.session.get('reset_otp_verified')
    if not mobile or not otp_verified:
        messages.error(request, 'Please complete OTP verification first.')
        return redirect('accounts:forgot_password')

    form = ResetPasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        AuthService.reset_password(mobile, form.cleaned_data['password1'])

        # Clean up session
        request.session.pop('reset_mobile', None)
        request.session.pop('reset_otp_verified', None)

        messages.success(request, 'Password reset successful. Please log in.')
        return redirect('accounts:login')

    return render(request, 'accounts/reset_password.html', {'form': form})


# ---------------------------------------------------------------------------
# Employee Management (admin only)
# ---------------------------------------------------------------------------

@login_required
@staff_required
def employee_list_view(request):
    """List all staff and admin users with optional search."""
    queryset = User.objects.filter(role__in=[User.Role.STAFF, User.Role.ADMIN])

    search = request.GET.get('q', '').strip()
    if search:
        queryset = queryset.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(mobile_number__icontains=search)
        )

    return render(request, 'accounts/employee_list.html', {
        'employees': queryset,
        'search': search,
    })


@login_required
@staff_required
def create_employee_view(request):
    """Create a new staff or admin employee account."""
    form = EmployeeCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(
            request,
            f'Employee "{user.get_full_name() or user.mobile_number}" created successfully.',
        )
        return redirect('accounts:employee_list')

    return render(request, 'accounts/employee_form.html', {'form': form})


@login_required
@staff_required
def employee_detail_view(request, pk):
    """View details and stats for an employee."""
    employee = get_object_or_404(User, pk=pk, role__in=[User.Role.STAFF, User.Role.ADMIN])

    from attendance.models import AttendanceLog
    from appointments.models import Appointment

    today = timezone.localdate()
    month_start = today.replace(day=1)

    # Attendance stats
    month_hours = AttendanceLog.active_objects.filter(
        user=employee, date__gte=month_start, duration__isnull=False
    ).aggregate(total=Sum('duration'))['total'] or timedelta()

    attendance_days = AttendanceLog.active_objects.filter(
        user=employee, date__gte=month_start
    ).values('date').distinct().count()

    # Appointment stats
    total_sessions = Appointment.active_objects.filter(
        staff=employee, status=Appointment.Status.COMPLETED
    ).count()

    upcoming = Appointment.active_objects.filter(
        staff=employee, date__gte=today, status=Appointment.Status.SCHEDULED
    ).count()

    assigned_clients_count = employee.assigned_clients.filter(is_deleted=False).count()

    # Format timedelta as HH:MM:SS
    total_seconds = int(month_hours.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    month_hours_display = f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    context = {
        'employee': employee,
        'month_hours': month_hours_display,
        'attendance_days': attendance_days,
        'total_sessions': total_sessions,
        'upcoming_appointments': upcoming,
        'assigned_clients': assigned_clients_count,
    }
    return render(request, 'accounts/employee_detail.html', context)
