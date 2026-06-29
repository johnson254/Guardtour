from api.services.gps import _haversine as _haversine_meters


def _point_in_polygon(lat, lng, polygon):
    """Ray-casting point-in-polygon. polygon = list of [lat, lng] points."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside
