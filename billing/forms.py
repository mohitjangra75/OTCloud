from django import forms

from billing.models import Expense, MonthlyBill, PaymentMode


class MonthlyBillForm(forms.ModelForm):
    """Create / edit a monthly billing row for one client + therapy type."""

    class Meta:
        model = MonthlyBill
        fields = [
            'client', 'therapy_type', 'month',
            'sessions_per_week', 'total_sessions',
            'package_amount', 'paid_amount', 'carry_forward',
            'payment_mode', 'paid_date', 'notes',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'therapy_type': forms.Select(attrs={'class': 'form-select'}),
            'month': forms.DateInput(attrs={'class': 'form-input', 'type': 'month'}),
            'sessions_per_week': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'total_sessions': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'package_amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'paid_amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'carry_forward': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'payment_mode': forms.Select(attrs={'class': 'form-select'}),
            'paid_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }

    def clean_month(self):
        m = self.cleaned_data.get('month')
        if m:
            return m.replace(day=1)
        return m


class BillPaymentForm(forms.Form):
    """Quick payment recorder against an existing bill."""
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
    )
    payment_mode = forms.ChoiceField(
        choices=[('', '---')] + list(PaymentMode.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    paid_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
    )


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'date', 'category', 'item', 'remarks', 'amount',
            'payment_mode', 'paid_to', 'paid_to_employee', 'status',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'item': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Stationery, Internet bill'}),
            'remarks': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Optional notes'}),
            'amount': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': 0}),
            'payment_mode': forms.Select(attrs={'class': 'form-select'}),
            'paid_to': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Vendor / payee name'}),
            'paid_to_employee': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }
