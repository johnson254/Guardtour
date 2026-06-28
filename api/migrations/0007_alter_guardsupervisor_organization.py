# Generated migration to make GuardSupervisor.organization nullable

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_handle_data_migration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='guardsupervisor',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guards_supervisors', to='api.organization'),
        ),
    ]