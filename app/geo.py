import math

EARTH_RADIUS_M = 6_371_000


def haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bounding_rect(lng: float, lat: float, radius_m: float):
    """중심점과 반경으로 (min_lng, min_lat, max_lng, max_lat) 사각형을 만든다."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlng = math.degrees(radius_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return (lng - dlng, lat - dlat, lng + dlng, lat + dlat)


def split_rect(rect):
    min_x, min_y, max_x, max_y = rect
    mid_x, mid_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    return [
        (min_x, min_y, mid_x, mid_y),
        (mid_x, min_y, max_x, mid_y),
        (min_x, mid_y, mid_x, max_y),
        (mid_x, mid_y, max_x, max_y),
    ]
