from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.validators import RegexValidator

User = get_user_model()

mobile_validator = RegexValidator(
    regex=r'^\+?[1-9]\d{9,14}$',
    message='Enter a valid mobile number (10-15 digits, optional leading +).',
)


def clean_mobile_input(value):
    """Strip dashes, spaces, and non-digit chars (except leading +)."""
    if value.startswith('+'):
        return '+' + ''.join(c for c in value[1:] if c.isdigit())
    return ''.join(c for c in value if c.isdigit())


class RegistrationForm(forms.Form):
    """Step 1: Collect mobile number, basic profile info, and send OTP."""
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'First Name',
            'autofocus': True,
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Last Name (optional)',
        }),
    )
    mobile_number = forms.CharField(
        max_length=15,
        validators=[mobile_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Mobile Number',
        }),
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Email (optional)',
        }),
    )
    role = forms.ChoiceField(
        choices=[
            ('', 'Select Role'),
            (User.Role.CLIENT, 'Client'),
            (User.Role.STAFF, 'Staff'),
        ],
        initial=User.Role.CLIENT,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
    )

    def clean_mobile_number(self):
        mobile = clean_mobile_input(self.cleaned_data['mobile_number'])
        if User.objects.filter(mobile_number=mobile).exists():
            raise forms.ValidationError('An account with this mobile number already exists.')
        return mobile


class OTPVerificationForm(forms.Form):
    """Step 2: Verify OTP code."""
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter 6-digit OTP',
            'autofocus': True,
            'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
        }),
    )

    def clean_otp(self):
        otp = self.cleaned_data['otp']
        if not otp.isdigit():
            raise forms.ValidationError('OTP must contain only digits.')
        return otp


class RegistrationCompleteForm(forms.Form):
    """Step 3: Set password after OTP verification (profile info collected in step 1)."""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password',
            'autofocus': True,
        }),
        validators=[validate_password],
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm Password',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data


class LoginForm(forms.Form):
    """Login with mobile number and password."""
    mobile_number = forms.CharField(
        max_length=15,
        validators=[mobile_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Mobile Number',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password',
        }),
    )

    def clean_mobile_number(self):
        return clean_mobile_input(self.cleaned_data['mobile_number'])


class ProfileForm(forms.ModelForm):
    """Edit user profile."""

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'profile_image']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'profile_image': forms.ClearableFileInput(attrs={'class': 'form-input-file'}),
        }


class EmployeeCreateForm(forms.ModelForm):
    """Admin form to create staff/admin employee accounts."""
    mobile_number = forms.CharField(
        max_length=15,
        validators=[mobile_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Mobile Number',
        }),
    )
    role = forms.ChoiceField(
        choices=[
            (User.Role.STAFF, 'Staff'),
            (User.Role.ADMIN, 'Admin'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Password',
        }),
        validators=[validate_password],
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm Password',
        }),
    )

    class Meta:
        model = User
        fields = ['mobile_number', 'first_name', 'last_name', 'email', 'role']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'First Name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Last Name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'Email (optional)',
            }),
        }

    def clean_mobile_number(self):
        mobile = clean_mobile_input(self.cleaned_data['mobile_number'])
        if User.objects.filter(mobile_number=mobile).exists():
            raise forms.ValidationError('An account with this mobile number already exists.')
        return mobile

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.is_verified = True
        if commit:
            user.save()
        return user


class ForgotPasswordForm(forms.Form):
    """Request OTP for password reset."""
    mobile_number = forms.CharField(
        max_length=15,
        validators=[mobile_validator],
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Mobile Number',
            'autofocus': True,
        }),
    )

    def clean_mobile_number(self):
        mobile = clean_mobile_input(self.cleaned_data['mobile_number'])
        if not User.objects.filter(mobile_number=mobile).exists():
            raise forms.ValidationError('No account found with this mobile number.')
        return mobile


class ResetPasswordForm(forms.Form):
    """Set new password after OTP verification."""
    password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'New Password',
        }),
        validators=[validate_password],
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': 'Confirm New Password',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password1')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data
