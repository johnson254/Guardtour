# Generated migration to handle data transition from UserProfile to GuardSupervisor

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_multi_tenant_redesign'),
    ]

    operations = [
        # Delete all devices that reference non-existent GuardSupervisor
        migrations.RunSQL(
            sql="UPDATE api_device SET user_id = NULL WHERE user_id NOT IN (SELECT id FROM api_guardsupervisor);",
            reverse_sql=migrations.RunSQL.noop
        ),
        # Delete all scanrecords that reference non-existent GuardSupervisor/route/checkpoint
        migrations.RunSQL(
            sql="UPDATE api_scanrecord SET guard_supervisor_id = NULL, route_id = NULL, checkpoint_id = NULL;",
            reverse_sql=migrations.RunSQL.noop
        ),
    ]