"""TMAP(SK open API) 보행자 경로 API로 실제 도보 소요시간을 구한다."""
import httpx

from .. import cache, config

URL = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
# TMAP 상품약관: API로 얻은 데이터는 저장 후 24시간 이상 사용할 수 없다.
CACHE_TTL = 23 * 3600


async def walking_time(client: httpx.AsyncClient, start: dict, end: dict) -> dict | None:
    """{'minutes': int, 'meters': int} 또는 실패 시 None."""
    if not config.TMAP_APP_KEY:
        return None
    key = f"{start['lng']:.5f},{start['lat']:.5f}->{end['lng']:.5f},{end['lat']:.5f}"
    cached = cache.get("tmap", key, ttl_seconds=CACHE_TTL)
    if cached is not None:
        return cached
    body = {
        "startX": str(start["lng"]),
        "startY": str(start["lat"]),
        "endX": str(end["lng"]),
        "endY": str(end["lat"]),
        "startName": "start",
        "endName": "end",
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
    }
    resp = await client.post(URL, json=body, headers={"appKey": config.TMAP_APP_KEY})
    if resp.status_code != 200:
        return None
    features = resp.json().get("features") or []
    if not features:
        return None
    props = features[0]["properties"]
    result = {"minutes": round(props["totalTime"] / 60), "meters": props["totalDistance"]}
    cache.put("tmap", key, result)
    return result
