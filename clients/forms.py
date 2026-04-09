from django import forms
from django.conf import settings

from clients.models import Client


class ClientForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
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
