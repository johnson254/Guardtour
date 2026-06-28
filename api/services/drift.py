from django.utils import timezone
from rest_framework import serializers


MAX_TIMESTAMP_DRIFT_SECONDS = 300


def validate_timestamp_drift(client_ts, server_now):
    if not client_ts:
        return None, False
    drift = int((server_now - client_ts).total_seconds())
    suspicious = abs(drift) > MAX_TIMESTAMP_DRIFT_SECONDS
    return drift, suspicious


def validate_sequence_id(device, sequence_id):
    if sequence_id is None:
        return True
    if sequence_id <= device.last_sequence_id:
        return False
    from api.models import Device
    Device.objects.filter(id=device.id, last_sequence_id__lt=sequence_id).update(
        last_sequence_id=sequence_id
    )
    return True
