import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
        ('salary', '0002_align_rules'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # SalarySetting: replace weekly target + per-extra-session with per-rating-point
        migrations.RemoveField(model_name='salarysetting', name='sessions_target_per_week'),
        migrations.RemoveField(model_name='salarysetting', name='incentive_per_extra_session'),
        migrations.AddField(
            model_name='salarysetting',
            name='incentive_per_rating_point',
            field=models.DecimalField(
                decimal_places=2, default=0,
                help_text=('Bonus per rating star received from clients (e.g., ₹100/point → '
                           '5★ rating = ₹500 bonus). Total = sum of stars across all client '
                           'ratings × this value.'),
                max_digits=10,
            ),
        ),

        # MonthlySalary: replace extra_sessions with rating fields
        migrations.RemoveField(model_name='monthlysalary', name='extra_sessions'),
        migrations.AddField(
            model_name='monthlysalary',
            name='total_ratings',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Number of client ratings received this month',
            ),
        ),
        migrations.AddField(
            model_name='monthlysalary',
            name='avg_rating',
            field=models.DecimalField(
                decimal_places=2, default=0,
                help_text='Average rating across all client feedback this month (0–5)',
                max_digits=3,
            ),
        ),

        # New PerformanceRating model
        migrations.CreateModel(
            name='PerformanceRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('month', models.DateField(help_text='First day of the rated month')),
                ('score', models.PositiveSmallIntegerField(choices=[(1, '1★ Poor'), (2, '2★ Below Average'), (3, '3★ Average'), (4, '4★ Good'), (5, '5★ Excellent')])),
                ('feedback', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ratings_given', to='clients.client')),
                ('therapist', models.ForeignKey(limit_choices_to={'role__in': ['staff', 'admin']}, on_delete=django.db.models.deletion.CASCADE, related_name='ratings_received', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-month', 'therapist__first_name'],
                'unique_together': {('client', 'therapist', 'month')},
            },
        ),
    ]
