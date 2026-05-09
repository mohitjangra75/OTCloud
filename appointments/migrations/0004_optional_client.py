import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
        ('appointments', '0003_appointment_needs_reassignment_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='appointment',
            name='client',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Linked client record. Optional — for trials, fill client_name instead.',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='appointments',
                to='clients.client',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='client_name',
            field=models.CharField(
                blank=True, max_length=120,
                help_text='Free-form name when no Client record exists yet (e.g. "Trial - Aanya Sharma").',
            ),
        ),
        migrations.AddField(
            model_name='appointment',
            name='client_mobile',
            field=models.CharField(
                blank=True, max_length=15,
                help_text='Optional mobile for trial / non-client appointments.',
            ),
        ),
    ]
