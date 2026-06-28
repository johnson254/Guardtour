import math
from datetime import timedelta


def _haversine(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _spherical_interpolate(lat1, lng1, lat2, lng2, ratio):
    lat1_r, lng1_r = math.radians(lat1), math.radians(lng1)
    lat2_r, lng2_r = math.radians(lat2), math.radians(lng2)

    x1 = math.cos(lat1_r) * math.cos(lng1_r)
    y1 = math.cos(lat1_r) * math.sin(lng1_r)
    z1 = math.sin(lat1_r)

    x2 = math.cos(lat2_r) * math.cos(lng2_r)
    y2 = math.cos(lat2_r) * math.sin(lng2_r)
    z2 = math.sin(lat2_r)

    x = x1 + (x2 - x1) * ratio
    y = y1 + (y2 - y1) * ratio
    z = z1 + (z2 - z1) * ratio

    mag = math.sqrt(x * x + y * y + z * z)
    if mag == 0:
        return lat1, lng1
    x, y, z = x / mag, y / mag, z / mag

    interp_lat = math.degrees(math.asin(max(-1.0, min(1.0, z))))
    interp_lng = math.degrees(math.atan2(y, x))
    return interp_lat, interp_lng


MAX_INTERPOLATION_GAP_SECONDS = 600


def correct_gps_trail(points, max_speed_ms=30.0, window_size=3):
    if len(points) < 2:
        return [dict(p, corrected=False) for p in points]

    n = len(points)
    cleaned = [dict(points[0], corrected=False)]
    for i in range(1, n):
        prev = cleaned[-1]
        p = points[i]
        dt = abs((p['recorded_at'] - prev['recorded_at']).total_seconds())

        if dt > MAX_INTERPOLATION_GAP_SECONDS:
            cleaned.append({'gap': True, 'recorded_at': prev['recorded_at'] + timedelta(seconds=MAX_INTERPOLATION_GAP_SECONDS)})
            cleaned.append(dict(p, corrected=False))
            continue

        d = _haversine(prev['lat'], prev['lng'], p['lat'], p['lng'])
        speed = d / dt if dt > 0 else 0
        if speed > max_speed_ms:
            ratio = min(1.0, max_speed_ms / speed) if speed > 0 else 1.0
            interp_lat, interp_lng = _spherical_interpolate(
                prev['lat'], prev['lng'], p['lat'], p['lng'], ratio
            )
            cleaned.append(dict(p, lat=interp_lat, lng=interp_lng, corrected=True))
        else:
            cleaned.append(dict(p, corrected=False))

    result = []
    half = window_size // 2
    for i in range(len(cleaned)):
        p = cleaned[i]
        if p.get('gap'):
            result.append(p)
            continue
        acc = p.get('accuracy') or 50.0
        start = max(0, i - half)
        end = min(len(cleaned), i + half + 1)
        wsum = 0.0
        lat_w = 0.0
        lng_w = 0.0
        for j in range(start, end):
            q = cleaned[j]
            if q.get('gap'):
                continue
            qacc = q.get('accuracy') or 50.0
            w = 1.0 / (qacc + 1.0)
            wsum += w
            lat_w += q['lat'] * w
            lng_w += q['lng'] * w
        smoothed_lat = lat_w / wsum if wsum > 0 else p['lat']
        smoothed_lng = lng_w / wsum if wsum > 0 else p['lng']
        is_corrected = p.get('corrected', False) or (abs(smoothed_lat - p['lat']) > 0.0001)
        result.append(dict(p, lat=smoothed_lat, lng=smoothed_lng, corrected=is_corrected))

    return result
