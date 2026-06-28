# Generated migration to make Dispatcher.organization nullable

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_guardsupervisor_operator_id'),
    ]

    operations = [
        migrations.AlterField(
            model_name='dispatcher',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='dispatchers', to='api.organization'),
        ),
    ]