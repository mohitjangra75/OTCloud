import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_replace_invoice_with_monthly'),
        ('clients', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('month', models.DateField(help_text='First day of the billing month')),
                ('invoice_number', models.CharField(max_length=30, unique=True)),
                ('total_sessions', models.PositiveIntegerField(default=0)),
                ('total_billed', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('total_paid', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('carry_forward', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('balance_due', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('last_session_count', models.PositiveIntegerField(default=0, help_text='Snapshot session count from last regeneration')),
                ('generated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='clients.client')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-month', 'client__first_name'],
                'unique_together': {('client', 'month')},
            },
        ),
    ]
