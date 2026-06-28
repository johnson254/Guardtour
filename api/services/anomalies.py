from api.services.gps import _haversine

MAX_HUMAN_WALKING_SPEED_M_PER_MIN = 120
GPS_INSTABILITY_HDOP_THRESHOLD = 6.0
GPS_STABLE_HDOP_THRESHOLD = 3.0
DRIFT_SPEED_M_PER_S = 0.5
PROLONGED_DWELL_MULTIPLIER = 2.5


def _sensor_confirms_presence(sensor_context):
    if not sensor_context or not isinstance(sensor_context, dict):
        return False
    pir = sensor_context.get('pir_triggered', False)
    proximity = sensor_context.get('proximity_score', 0)
    accel = sensor_context.get('accel_pattern', '')
    return bool(pir) and proximity >= 0.8 and accel in ('steady', 'walking')


def _sensor_mismatch(sensor_context):
    if not sensor_context or not isinstance(sensor_context, dict):
        return False
    accel = sensor_context.get('accel_pattern', '')
    proximity = sensor_context.get('proximity_score', 0)
    return accel == 'erratic' or proximity < 0.4


def _detect_anomalies(points, checkpoint, continuous_presence_seconds):
    flags = []
    if len(points) < 2:
        return flags
    jump_count = 0
    prev_hdop = None
    prev_point = None
    total_inside_time = 0
    for i, p in enumerate(points):
        if i == 0:
            prev_point = p
            if (p.get('accuracy') or 0) > 0:
                prev_hdop = p['accuracy']
            continue
        prev = prev_point
        dt = (p['recorded_at'] - prev['recorded_at']).total_seconds()
        if dt > 0:
            dist = _haversine(prev['lat'], prev['lng'], p['lat'], p['lng'])
            speed = dist / dt * 60
            if speed > MAX_HUMAN_WALKING_SPEED_M_PER_MIN:
                jump_count += 1
        hdop = p.get('accuracy')
        if hdop and prev_hdop:
            if prev_hdop < GPS_STABLE_HDOP_THRESHOLD and hdop > GPS_INSTABILITY_HDOP_THRESHOLD:
                flags.append('gps_instability')
        if prev_point and dt > 0:
            dist = _haversine(prev['lat'], prev['lng'], p['lat'], p['lng'])
            if DRIFT_SPEED_M_PER_S * dt <= dist <= MAX_HUMAN_WALKING_SPEED_M_PER_MIN * dt / 60:
                total_inside_time += dt
        prev_point = p
        if hdop:
            prev_hdop = hdop
    if jump_count > 3:
        flags.append('sudden_jump')
    if total_inside_time > 0 and total_inside_time == continuous_presence_seconds:
        if continuous_presence_seconds > 0:
            flags.append('prolonged_drift')
    dwell_required = (checkpoint.dwell_time or 0) * 60
    if dwell_required > 0 and continuous_presence_seconds > dwell_required * PROLONGED_DWELL_MULTIPLIER:
        flags.append('prolonged_dwell')
    return list(set(flags))
