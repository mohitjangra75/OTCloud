import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0001_initial'),
        ('billing', '0001_initial'),
        ('clients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.DeleteModel(name='InvoiceItem'),
        migrations.DeleteModel(name='Invoice'),

        migrations.CreateModel(
            name='MonthlyBill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('month', models.DateField(help_text='First day of the billing month')),
                ('sessions_per_week', models.PositiveIntegerField(default=0)),
                ('total_sessions', models.PositiveIntegerField(default=0)),
                ('package_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('paid_amount', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('carry_forward', models.DecimalField(decimal_places=2, default=0, help_text='Carried from previous month dues', max_digits=10)),
                ('payment_mode', models.CharField(blank=True, choices=[('cash', 'Cash'), ('upi', 'UPI'), ('bank', 'Bank Transfer'), ('card', 'Card'), ('cheque', 'Cheque'), ('other', 'Other')], max_length=15)),
                ('paid_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('unpaid', 'Unpaid'), ('partial', 'Partial'), ('paid', 'Paid')], default='unpaid', max_length=10)),
                ('notes', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='monthly_bills', to='clients.client')),
                ('therapy_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='monthly_bills', to='appointments.therapytype')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-month', 'client__first_name'],
                'unique_together': {('client', 'therapy_type', 'month')},
            },
        ),
        migrations.CreateModel(
            name='Expense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('date', models.DateField()),
                ('category', models.CharField(choices=[('expense', 'Org Expense'), ('reimbursement', 'Reimbursement')], default='expense', max_length=20)),
                ('item', models.CharField(max_length=255)),
                ('remarks', models.CharField(blank=True, max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('payment_mode', models.CharField(blank=True, choices=[('cash', 'Cash'), ('upi', 'UPI'), ('bank', 'Bank Transfer'), ('card', 'Card'), ('cheque', 'Cheque'), ('other', 'Other')], max_length=15)),
                ('paid_to', models.CharField(blank=True, help_text='Vendor name (for org expenses)', max_length=120)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('reimbursed', 'Reimbursed'), ('rejected', 'Rejected')], default='approved', max_length=15)),
                ('paid_to_employee', models.ForeignKey(blank=True, help_text='Employee being reimbursed (if reimbursement)', limit_choices_to={'role__in': ['staff', 'admin']}, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reimbursements_received', to=settings.AUTH_USER_MODEL)),
                ('paid_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='expenses_paid', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-id'],
            },
        ),
    ]
