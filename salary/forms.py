from django import forms

from salary.models import PerformanceRating, SalarySetting


class SalarySettingForm(forms.ModelForm):
    class Meta:
        model = SalarySetting
        fields = [
            'base_monthly_salary',
            'deduction_per_absent_day',
            'incentive_per_rating_point',
            'notes',
        ]
        widgets = {
            'base_monthly_salary': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'deduction_per_absent_day': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'incentive_per_rating_point': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }


class RatingForm(forms.ModelForm):
    class Meta:
        model = PerformanceRating
        fields = ['score', 'feedback']
        widgets = {
            'score': forms.RadioSelect(),
            'feedback': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 3,
                'placeholder': "How was your therapist this month? (optional)",
            }),
        }
