from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='preferred_days',
            field=models.CharField(
                blank=True, max_length=40,
                help_text='Comma-separated weekday codes the client prefers, e.g. "mon,wed,fri"',
            ),
        ),
        migrations.AddField(
            model_name='client',
            name='preferred_time_start',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='preferred_time_end',
            field=models.TimeField(blank=True, null=True),
        ),
    ]
