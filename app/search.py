"""기준 위치 → 반경 내 음식점 수집(카카오맵에 검색되는 가게) → 소요시간 계산 → 필터·정렬을 묶는 검색 흐름."""
import asyncio

import httpx

from . import config, subway
from .clients import kakao, tmap
from .geo import haversine_m

CONCURRENCY = 5


def _estimate_walk_minutes(distance_m: float) -> int:
    return round(distance_m * config.DETOUR_FACTOR / config.WALK_SPEED_M_PER_MIN)


SORTS = ("spread", "time", "distance")
WALK_AREA = "출발지 도보권"


async def search(
    query: str,
    mode: str,
    minutes: int,
    offset: int = 0,
    limit: int = 200,
    categories: list[str] | None = None,
    areas: list[str] | None = None,
    sort: str = "spread",
) -> dict:
    if mode not in ("walk", "transit"):
        raise ValueError("mode 는 walk 또는 transit 이어야 합니다.")
    if sort not in SORTS:
        raise ValueError(f"sort 는 {', '.join(SORTS)} 중 하나여야 합니다.")

    notes = []
    async with httpx.AsyncClient(timeout=15) as client:
        center = await kakao.resolve_location(client, query)
        if mode == "walk":
            places = await _walk_places(client, center, minutes, notes)
        else:
            places = await _transit_places(client, center, minutes, notes)

    results = [p for p in places if p["travel_minutes"] <= minutes]
    for p in results:
        p["category_group"] = _category_group(p["category_full"])
        p["area"] = _area(p, mode)

    # 카테고리 집계는 지역 필터만, 지역 집계는 카테고리 필터만 적용한 상태로 센다. (선택을 바꿔 볼 수 있게)
    in_area = [p for p in results if not areas or p["area"] in areas]
    in_cat = [p for p in results if not categories or p["category_group"] in categories]
    filtered = [p for p in in_area if not categories or p["category_group"] in categories]

    ordered = _sort(filtered, sort)
    page = ordered[offset : offset + limit]
    return {
        "center": center, "mode": mode, "minutes": minutes, "sort": sort,
        "total": len(results), "count": len(filtered), "offset": offset, "items": page, "notes": notes,
        "facets": {"categories": _category_facet(in_area), "areas": _area_facet(in_cat)},
    }


def _category_group(category_full: str) -> str:
    """'음식점 > 한식 > 국밥' → '한식'"""
    parts = [s.strip() for s in category_full.split(">")]
    return parts[1] if len(parts) > 1 else "기타"


def _area(p: dict, mode: str) -> str:
    if mode == "transit":
        t = p.get("transit") or {}
        return f"{t['station']}역 주변" if t.get("station") else WALK_AREA
    # 도보 모드: 지번 주소의 동/가/리 ('서울 강남구 역삼동 858' → '역삼동')
    for token in (p.get("address") or "").split()[1:]:
        if token[-1:] in ("동", "가", "리", "읍", "면") and not token[:-1].isdigit():
            return token
    return "기타"


def _sort(items: list[dict], sort: str) -> list[dict]:
    by_time = sorted(items, key=lambda p: (p["travel_minutes"], p["distance_m"]))
    if sort == "time":
        return by_time
    if sort == "distance":
        return sorted(items, key=lambda p: p["distance_m"])
    # spread: 지역별로 시간순 줄을 세운 뒤, 가까운 지역부터 한 곳씩 번갈아 꺼낸다.
    groups: dict[str, list] = {}
    for p in by_time:
        groups.setdefault(p["area"], []).append(p)
    queues = sorted(groups.values(), key=lambda g: g[0]["travel_minutes"])
    out = []
    while queues:
        for q in queues:
            out.append(q.pop(0))
        queues = [q for q in queues if q]
    return out


def _category_facet(items: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for p in items:
        counts[p["category_group"]] = counts.get(p["category_group"], 0) + 1
    return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]


def _area_facet(items: list[dict]) -> list[dict]:
    stats: dict[str, dict] = {}
    for p in items:
        s = stats.setdefault(p["area"], {"name": p["area"], "count": 0, "min_minutes": p["travel_minutes"]})
        s["count"] += 1
        s["min_minutes"] = min(s["min_minutes"], p["travel_minutes"])
    return sorted(stats.values(), key=lambda s: (s["min_minutes"], -s["count"]))


def _with_distance(center: dict, places: list[dict]) -> list[dict]:
    for p in places:
        p["distance_m"] = round(haversine_m(center["lng"], center["lat"], p["lng"], p["lat"]))
        p["walk"] = {"minutes": _estimate_walk_minutes(p["distance_m"]), "estimated": True}
        p["transit"] = None
    return places


async def _walk_places(client, center, minutes, notes):
    # 직선거리는 실제 경로보다 항상 짧으므로, '이 시간 동안 직선으로 갈 수 있는 거리'를 1차 반경으로 쓴다.
    radius = minutes * config.WALK_SPEED_M_PER_MIN
    places = _with_distance(center, await kakao.restaurants_within(client, center["lng"], center["lat"], radius))
    places = sorted((p for p in places if p["distance_m"] <= radius), key=lambda p: p["distance_m"])

    if not config.TMAP_APP_KEY:
        notes.append("TMAP 키가 없어 도보 시간은 직선거리 기반 추정치입니다.")
    else:
        # 무료 쿼터 보호: 가까운 순으로 정해진 개수만 실제 경로 API를 호출한다.
        routed = places[: config.MAX_ROUTE_CALLS_PER_SEARCH]
        if len(places) > len(routed):
            notes.append(
                f"후보 {len(places)}곳 중 가까운 {len(routed)}곳만 실제 경로로 계산했고, 나머지는 직선거리 기반 추정치입니다."
            )
        sem = asyncio.Semaphore(CONCURRENCY)

        async def route(p):
            async with sem:
                r = await tmap.walking_time(client, center, p)
                if r:
                    p["walk"] = {**r, "estimated": False}

        await asyncio.gather(*(route(p) for p in routed))

    for p in places:
        p["travel_minutes"] = p["walk"]["minutes"]
    return places


async def _transit_places(client, center, minutes, notes):
    """지하철망 추정: 출발지 도보권 + 시간 안에 닿는 역마다 남은 시간만큼의 도보권에서 음식점을 모은다."""
    stations = subway.reachable_stations(center, minutes)
    if subway.load_graph() is None:
        notes.append("지하철 노선망 데이터가 없어 도보권만 검색했습니다. (python -m app.subway 로 생성)")
    notes.append("대중교통 시간은 서울 지하철 1~8호선 기준 추정치입니다. 버스 포함 정확한 경로는 가게별 '정확한 경로'로 확인하세요.")

    # 검색할 원: (중심, 반경). 같은 역의 여러 노선은 가장 빨리 닿는 것 하나만.
    circles = [(center, min(minutes, subway.ACCESS_WALK_MAX_MIN) * config.WALK_SPEED_M_PER_MIN)]
    best_by_name = {}
    for s in stations.values():
        if s["name"] not in best_by_name or s["minutes"] < best_by_name[s["name"]]["minutes"]:
            best_by_name[s["name"]] = s
    for s in best_by_name.values():
        remaining = minutes - s["minutes"]
        radius = min(remaining * config.WALK_SPEED_M_PER_MIN / config.DETOUR_FACTOR, subway.EGRESS_WALK_MAX_M)
        if radius >= 100:
            circles.append((s, radius))

    sem = asyncio.Semaphore(4)

    async def fetch(c, r):
        async with sem:
            found = await kakao.restaurants_within(client, c["lng"], c["lat"], r)
            return [p for p in found if haversine_m(c["lng"], c["lat"], p["lng"], p["lat"]) <= r]

    merged = {}
    for batch in await asyncio.gather(*(fetch(c, r) for c, r in circles)):
        for p in batch:
            merged[p["id"]] = p
    places = _with_distance(center, list(merged.values()))

    for p in places:
        est = subway.estimate(stations, p)
        if est and est["minutes"] < p["walk"]["minutes"]:
            p["transit"] = est
            p["travel_minutes"] = est["minutes"]
        else:
            p["transit"] = {"walk_only": True}
            p["travel_minutes"] = p["walk"]["minutes"]
    return places
