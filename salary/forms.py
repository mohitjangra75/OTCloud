from django import forms

from salary.models import SalarySetting


class SalarySettingForm(forms.ModelForm):
    class Meta:
        model = SalarySetting
        fields = [
            'base_monthly_salary',
            'deduction_per_absent_day',
            'sessions_target_per_week',
            'incentive_per_extra_session',
            'notes',
        ]
        widgets = {
            'base_monthly_salary': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'deduction_per_absent_day': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'sessions_target_per_week': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'incentive_per_extra_session': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }
