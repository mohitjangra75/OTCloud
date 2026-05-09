from django import forms

from lms.models import Lead, FollowUp


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ['name', 'mobile', 'email', 'source', 'status', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Full name',
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Mobile number',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'Email (optional)',
            }),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
            }),
        }


class FollowUpForm(forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ['follow_up_date', 'notes']
        widgets = {
            'follow_up_date': forms.DateTimeInput(attrs={
                'class': 'form-input',
                'type': 'datetime-local',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Follow-up notes',
            }),
        }
