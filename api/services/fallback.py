from api.services.anomalies import _sensor_confirms_presence, _sensor_mismatch


def apply_sensor_fallback(validity, sensor_context, anomaly_flags, result):
    sensor_aided = False
    if sensor_context:
        if _sensor_confirms_presence(sensor_context):
            sensor_aided = True
            result['sensor_aided'] = True
            result['verification_notes'] += ' sensor_confirmed_presence'
            if validity < 0.75:
                validity = 0.75
        elif _sensor_mismatch(sensor_context):
            anomaly_flags.append('sensor_mismatch')
            result['anomaly_flags'] = anomaly_flags
            result['verification_notes'] += ' sensor_mismatch'
            validity *= 0.5
    return validity, sensor_aided
