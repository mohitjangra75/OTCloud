from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('salary', '0001_initial'),
    ]

    operations = [
        # SalarySetting: drop old fields, add new fields
        migrations.RemoveField(
            model_name='salarysetting',
            name='incentive_per_session',
        ),
        migrations.RemoveField(
            model_name='salarysetting',
            name='cut_off_threshold_days',
        ),
        migrations.RemoveField(
            model_name='salarysetting',
            name='cut_off_amount',
        ),
        migrations.AddField(
            model_name='salarysetting',
            name='deduction_per_absent_day',
            field=models.DecimalField(
                decimal_places=2, default=0,
                help_text='Amount cut from base for every absent working day (half-days = half this)',
                max_digits=10,
            ),
        ),
        migrations.AddField(
            model_name='salarysetting',
            name='sessions_target_per_week',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Sessions per week considered "as expected". 0 = no target',
            ),
        ),
        migrations.AddField(
            model_name='salarysetting',
            name='incentive_per_extra_session',
            field=models.DecimalField(
                decimal_places=2, default=0,
                help_text='Bonus added for each session beyond the weekly target (summed across weeks in the month)',
                max_digits=10,
            ),
        ),
        migrations.AlterField(
            model_name='salarysetting',
            name='base_monthly_salary',
            field=models.DecimalField(
                decimal_places=2, default=0,
                help_text='Salary if 6-day week is fully attended (base for the month)',
                max_digits=10,
            ),
        ),

        # MonthlySalary: drop per_day_rate + cut_off, add extra_sessions
        migrations.RemoveField(
            model_name='monthlysalary',
            name='per_day_rate',
        ),
        migrations.RemoveField(
            model_name='monthlysalary',
            name='cut_off',
        ),
        migrations.AddField(
            model_name='monthlysalary',
            name='extra_sessions',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Sessions beyond the weekly target across all weeks of the month',
            ),
        ),
    ]
