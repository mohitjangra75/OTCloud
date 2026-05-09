from django import forms

from accounts.models import User
from appointments.models import Appointment, TherapyType
from clients.models import Client


class AppointmentForm(forms.ModelForm):
    """Appointment create/edit form.

    The client identity is collected as a free-form text field so trial /
    walk-in appointments can be booked without first creating a Client record.
    If the typed name matches an existing Client, we link it; otherwise the
    raw text is stored on `client_name` for display.
    """

    client_mobile = forms.CharField(
        label='Client Mobile',
        max_length=15,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': '+91 9XXXXXXXXX',
        }),
        help_text='Used to find/create the client. Required.',
    )
    client_name = forms.CharField(
        label='Client Name (optional)',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'e.g. Aanya Sharma',
            'autocomplete': 'off',
        }),
        help_text='Optional. New trial clients will be saved as "Trial - {name}".',
    )

    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
    )
    start_time = forms.ChoiceField(
        label='Start Time',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Pick from the available slots (45-min intervals, 9 AM – 6 PM).',
    )

    class Meta:
        model = Appointment
        fields = [
            'client_mobile',
            'client_name',
            'staff',
            'therapy_type',
            'date',
            'start_time',
            'notes',
        ]
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'therapy_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Lazy import to avoid circular dependency
        from appointments.services import AppointmentService

        self.fields['staff'].queryset = User.objects.filter(role__in=['staff', 'admin'], is_active=True)
        self.fields['therapy_type'].queryset = TherapyType.active_objects.all()
        self.fields['therapy_type'].required = True

        # Build slot choices from the centralised time-slot list
        slot_choices = [('', 'Pick a time slot…')]
        for t, label in AppointmentService.get_time_slots():
            slot_choices.append((t.strftime('%H:%M'), label))
        self.fields['start_time'].choices = slot_choices

        # When editing, pre-fill from instance
        if self.instance and self.instance.pk:
            if self.instance.client_id and self.instance.client:
                self.fields['client_name'].initial = self.instance.client.full_name
                self.fields['client_mobile'].initial = self.instance.client.mobile_number
            else:
                self.fields['client_name'].initial = self.instance.client_name
                self.fields['client_mobile'].initial = self.instance.client_mobile
            if self.instance.start_time:
                self.fields['start_time'].initial = self.instance.start_time.strftime('%H:%M')

    def clean(self):
        cleaned_data = super().clean()

        # Convert the slot string ("14:30") to a datetime.time
        import datetime as _dt
        from django.utils import timezone as _tz
        slot_str = cleaned_data.get('start_time')
        therapy = cleaned_data.get('therapy_type')
        date_ = cleaned_data.get('date')
        if slot_str:
            try:
                hh, mm = slot_str.split(':')
                start_t = _dt.time(int(hh), int(mm))
            except (ValueError, AttributeError):
                raise forms.ValidationError({'start_time': 'Invalid time slot.'})
            cleaned_data['start_time'] = start_t

            # Reject past slots when the date is today
            if date_:
                now = _tz.localtime()
                appt_naive = _dt.datetime.combine(date_, start_t)
                if _tz.is_aware(now):
                    appt_dt = _tz.make_aware(appt_naive, _tz.get_current_timezone())
                else:
                    appt_dt = appt_naive
                if appt_dt <= now:
                    raise forms.ValidationError(
                        {'start_time': 'That slot is already in the past — pick a future one.'}
                    )

            # Auto-derive end_time from therapy duration (default 45 min)
            duration = therapy.duration if therapy else 45
            end_dt = (_dt.datetime.combine(_dt.date.today(), start_t)
                      + _dt.timedelta(minutes=duration))
            cleaned_data['end_time'] = end_dt.time()

        # Resolve mobile → existing Client. Trial flag if no match.
        mobile = (cleaned_data.get('client_mobile') or '').strip()
        typed_name = (cleaned_data.get('client_name') or '').strip()
        if mobile:
            existing = Client.active_objects.filter(mobile_number=mobile).first()
            if existing:
                cleaned_data['_resolved_client'] = existing
                # If user didn't type a name, fall back to the linked client's name
                if not typed_name:
                    cleaned_data['client_name'] = existing.full_name
            else:
                # No client matched → it's a trial. Prefix with "Trial - " when a
                # name was typed; otherwise just use the mobile as the label.
                if typed_name:
                    if not typed_name.lower().startswith('trial'):
                        cleaned_data['client_name'] = f"Trial - {typed_name}"
                else:
                    cleaned_data['client_name'] = f"Trial - {mobile}"
        return cleaned_data

    def save(self, commit=True):
        from appointments.services import _staff_is_on_leave

        appointment = super().save(commit=False)
        # Wire client linkage based on resolution
        cd = self.cleaned_data
        resolved = cd.get('_resolved_client')
        appointment.client = resolved
        appointment.client_name = (cd.get('client_name') or '').strip()
        appointment.client_mobile = (cd.get('client_mobile') or '').strip()

        # Apply the auto-derived end_time from clean()
        if cd.get('start_time'):
            appointment.start_time = cd['start_time']
        if cd.get('end_time'):
            appointment.end_time = cd['end_time']
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
