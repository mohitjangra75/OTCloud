from django import forms

from accounts.models import User
from appointments.models import Appointment, TherapyType
from clients.models import Client


class AppointmentForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )
    end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )

    class Meta:
        model = Appointment
        fields = [
            'client',
            'staff',
            'therapy_type',
            'date',
            'start_time',
            'end_time',
            'notes',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'therapy_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].queryset = Client.active_objects.all()
        self.fields['staff'].queryset = User.objects.filter(role__in=['staff', 'admin'], is_active=True)
        self.fields['therapy_type'].queryset = TherapyType.active_objects.all()
        self.fields['therapy_type'].required = True

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned_data

    def save(self, commit=True):
        from appointments.services import _staff_is_on_leave

        appointment = super().save(commit=False)
        appointment.calculate_price()

        leave_mark = _staff_is_on_leave(appointment.staff, appointment.date)
        if leave_mark:
            appointment.needs_reassignment = True
            appointment.reassignment_reason = (
                f"Staff is absent on {appointment.date:%d %b} — please reassign."
            )

        if commit:
            appointment.save()
        return appointment


class RescheduleForm(forms.Form):
    new_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
    )
    new_start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )
    new_end_time = forms.TimeField(
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('new_start_time')
        end_time = cleaned_data.get('new_end_time')
        if start_time and end_time and start_time >= end_time:
            raise forms.ValidationError("End time must be after start time.")
        return cleaned_data


class ReassignStaffForm(forms.Form):
    new_staff = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=['staff', 'admin'], is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Assign to',
    )

    def __init__(self, *args, exclude_date=None, **kwargs):
        super().__init__(*args, **kwargs)
        if exclude_date:
            from attendance.models import AttendanceMark
            on_leave_ids = AttendanceMark.active_objects.filter(
                date=exclude_date,
                status=AttendanceMark.Status.LEAVE,
            ).values_list('user_id', flat=True)
            self.fields['new_staff'].queryset = (
                self.fields['new_staff'].queryset.exclude(id__in=list(on_leave_ids))
            )
