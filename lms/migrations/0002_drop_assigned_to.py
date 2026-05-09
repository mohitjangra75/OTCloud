from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('lms', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='lead',
            name='assigned_to',
        ),
    ]
