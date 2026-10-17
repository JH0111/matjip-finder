"""카카오 로컬 API: 위치 → 좌표 변환, 반경 내 음식점(FD6) 수집.

카테고리 검색은 한 조건당 최대 45건(15건 x 3페이지)까지만 주기 때문에,
결과가 45건을 넘는 구역은 사각형을 4등분해서 다시 검색한다.
"""
import httpx

from .. import cache, config
from ..geo import bounding_rect, split_rect

BASE = "https://dapi.kakao.com/v2/local"
PAGE_SIZE = 15
MAX_RESULTS_PER_QUERY = 45
MAX_SPLIT_DEPTH = 4
DAY = 24 * 3600


class KakaoError(RuntimeError):
    pass


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    if not config.KAKAO_REST_API_KEY:
        raise KakaoError("카카오 REST API 키가 없습니다. 오른쪽 위 'API 키 설정'에서 입력하세요.")
    key = f"{path}?{sorted(params.items())}"
    cached = cache.get("kakao", key, ttl_seconds=DAY)
    if cached is not None:
        return cached
    resp = await client.get(
        f"{BASE}{path}", params=params, headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"}
    )
    if resp.status_code != 200:
        raise KakaoError(f"카카오 API 오류 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    cache.put("kakao", key, data)
    return data


async def resolve_location(client: httpx.AsyncClient, query: str) -> dict:
    """'강남역', '서울 중구 세종대로 110' 같은 입력을 좌표로 바꾼다. 주소 검색 → 키워드 검색 순."""
    data = await _get(client, "/search/address.json", {"query": query, "size": 1})
    if data["documents"]:
        doc = data["documents"][0]
        return {"name": doc["address_name"], "lng": float(doc["x"]), "lat": float(doc["y"])}
    data = await _get(client, "/search/keyword.json", {"query": query, "size": 1})
    if data["documents"]:
        doc = data["documents"][0]
        return {"name": doc["place_name"], "lng": float(doc["x"]), "lat": float(doc["y"])}
    raise KakaoError(f"'{query}' 위치를 찾지 못했습니다.")


async def _search_rect(client: httpx.AsyncClient, rect, depth: int, out: dict):
    rect_param = ",".join(f"{v:.6f}" for v in rect)
    first = await _get(
        client,
        "/search/category.json",
        {"category_group_code": "FD6", "rect": rect_param, "page": 1, "size": PAGE_SIZE},
    )
    total = first["meta"]["total_count"]
    if total > MAX_RESULTS_PER_QUERY and depth < MAX_SPLIT_DEPTH:
        for sub in split_rect(rect):
            await _search_rect(client, sub, depth + 1, out)
        return

    page_data, page = first, 1
    while True:
        for doc in page_data["documents"]:
            out[doc["id"]] = doc
        if page_data["meta"]["is_end"] or page >= MAX_RESULTS_PER_QUERY // PAGE_SIZE:
            break
        page += 1
        page_data = await _get(
            client,
            "/search/category.json",
            {"category_group_code": "FD6", "rect": rect_param, "page": page, "size": PAGE_SIZE},
        )


async def restaurants_within(client: httpx.AsyncClient, lng: float, lat: float, radius_m: float) -> list[dict]:
    found: dict[str, dict] = {}
    await _search_rect(client, bounding_rect(lng, lat, radius_m), 0, found)
    return [
        {
            "id": doc["id"],
            "name": doc["place_name"],
            "category": doc["category_name"].split(" > ")[-1],
            "category_full": doc["category_name"],
            "phone": doc["phone"],
            "address": doc["address_name"],
            "road_address": doc["road_address_name"],
            "lng": float(doc["x"]),
            "lat": float(doc["y"]),
            "kakao_url": doc["place_url"],
        }
        for doc in found.values()
    ]
