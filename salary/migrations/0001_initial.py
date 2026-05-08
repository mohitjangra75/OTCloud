import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SalarySetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('base_monthly_salary', models.DecimalField(decimal_places=2, default=0, help_text='Gross monthly salary if all days are present', max_digits=10)),
                ('incentive_per_session', models.DecimalField(decimal_places=2, default=0, help_text='Bonus added per completed session', max_digits=10)),
                ('cut_off_threshold_days', models.PositiveIntegerField(default=0, help_text='If absent days exceed this, apply the flat cut-off below. 0 = disabled')),
                ('cut_off_amount', models.DecimalField(decimal_places=2, default=0, help_text='Flat extra deduction once threshold is exceeded', max_digits=10)),
                ('notes', models.TextField(blank=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('employee', models.OneToOneField(limit_choices_to={'role__in': ['staff', 'admin']}, on_delete=django.db.models.deletion.CASCADE, related_name='salary_setting', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['employee__first_name', 'employee__last_name'],
            },
        ),
        migrations.CreateModel(
            name='MonthlySalary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('month', models.DateField(help_text='First day of the salary month')),
                ('total_working_days', models.PositiveIntegerField(default=0)),
                ('present_days', models.PositiveIntegerField(default=0)),
                ('half_days', models.PositiveIntegerField(default=0)),
                ('absent_days', models.PositiveIntegerField(default=0)),
                ('total_sessions', models.PositiveIntegerField(default=0)),
                ('base_monthly_salary', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('per_day_rate', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('deduction', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('cut_off', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('incentive', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('in_hand_salary', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('generated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('employee', models.ForeignKey(limit_choices_to={'role__in': ['staff', 'admin']}, on_delete=django.db.models.deletion.CASCADE, related_name='monthly_salaries', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-month', 'employee__first_name'],
                'unique_together': {('employee', 'month')},
            },
        ),
    ]
