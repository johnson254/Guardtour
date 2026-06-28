# Generated migration to add operator_id field to GuardSupervisor

from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_alter_guardsupervisor_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='guardsupervisor',
            name='operator_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]