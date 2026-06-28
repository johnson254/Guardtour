# Generated migration for adding is_completed field to ShiftAssignment

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_guardsupervisor_user_alter_patrolroute_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='shiftassignment',
            name='is_completed',
            field=models.BooleanField(default=False, help_text='True when all checkpoints have been scanned'),
        ),
    ]