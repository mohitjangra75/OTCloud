from django import forms

from accounts.models import User
from clients.models import Client


DAY_CHOICES = [
    ('mon', 'Mon'), ('tue', 'Tue'), ('wed', 'Wed'),
    ('thu', 'Thu'), ('fri', 'Fri'), ('sat', 'Sat'), ('sun', 'Sun'),
]


class ClientForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
    )

    preferred_days = forms.MultipleChoiceField(
        required=False,
        choices=DAY_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'pref-days'}),
        help_text='Days the client prefers therapy on',
    )
    preferred_time_start = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )
    preferred_time_end = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time', 'class': 'form-input'}),
    )

    assigned_therapist = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(
            role__in=[User.Role.STAFF, User.Role.ADMIN],
            is_active=True,
        ).order_by('first_name', 'last_name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='— Unassigned —',
        help_text='Staff member responsible for this client',
    )

    class Meta:
        model = Client
        fields = [
            'first_name',
            'last_name',
            'mobile_number',
            'email',
            'date_of_birth',
            'gender',
            'address',
            'medical_history',
            'preferred_days',
            'preferred_time_start',
            'preferred_time_end',
            'assigned_therapist',
            'notes',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'medical_history': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill preferred_days from the comma-separated DB value
        if self.instance and self.instance.preferred_days:
            self.initial['preferred_days'] = [
                d.strip() for d in self.instance.preferred_days.split(',') if d.strip()
            ]

    def clean_preferred_days(self):
        days = self.cleaned_data.get('preferred_days') or []
        return ','.join(days)
