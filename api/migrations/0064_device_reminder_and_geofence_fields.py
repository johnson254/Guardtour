from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0063_backend_fixes_operator_null_and_checkpoint_setnull'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='last_reminder_at',
            field=models.DateTimeField(blank=True, help_text='When the last lead-time reminder TTS was spoken', null=True),
        ),
        migrations.AddField(
            model_name='device',
            name='geofence_states',
            field=models.JSONField(blank=True, default=dict, help_text='Tracks entered geofence IDs to avoid duplicate TTS: {map_object_id: entered_at_iso}', null=True),
        ),
        migrations.AddField(
            model_name='device',
            name='tts_acked',
            field=models.BooleanField(blank=True, default=True, help_text='True when device confirmed receipt of last tts_pending. If False, resend on next heartbeat.'),
        ),
    ]
