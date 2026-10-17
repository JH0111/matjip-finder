"""ODsay LAB 대중교통 길찾기 API. 사용자가 가게를 클릭했을 때만 호출한다.

- 무료(Basic) 요금제는 하루 30건.
- 이용약관상 API 결과 데이터를 동의 없이 저장할 수 없으므로 캐시하지 않는다.
"""
import httpx

from .. import config

URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
TOO_CLOSE_CODE = "-98"  # 출발지와 도착지가 700m 이내라 대중교통 경로를 주지 않는 경우

_TRAFFIC_TYPES = {1: "지하철", 2: "버스", 3: "도보"}


class OdsayError(RuntimeError):
    pass


def _leg_label(sub: dict) -> str:
    kind = _TRAFFIC_TYPES.get(sub["trafficType"], "?")
    lane = (sub.get("lane") or [{}])[0]
    name = lane.get("name") or lane.get("busNo") or ""
    if sub["trafficType"] == 3:
        return f"도보 {sub.get('sectionTime', 0)}분"
    return f"{kind} {name} {sub.get('startName', '')}→{sub.get('endName', '')}".strip()


async def transit_route(client: httpx.AsyncClient, start: dict, end: dict) -> dict:
    """{'minutes', 'transfers', 'fare', 'legs': [...]} 또는 {'too_close': True}. 실패 시 OdsayError."""
    if not config.ODSAY_API_KEY:
        raise OdsayError("ODsay API 키가 없습니다. 오른쪽 위 'API 키 설정'에서 입력하세요.")
    params = {"SX": start["lng"], "SY": start["lat"], "EX": end["lng"], "EY": end["lat"], "apiKey": config.ODSAY_API_KEY}
    resp = await client.get(URL, params=params)
    if resp.status_code != 200:
        raise OdsayError(f"ODsay 오류 {resp.status_code}")
    data = resp.json()
    if "error" in data:
        err = data["error"]
        if isinstance(err, list):
            err = err[0] if err else {}
        if str(err.get("code")) == TOO_CLOSE_CODE:
            return {"too_close": True}
        raise OdsayError(f"ODsay: {err.get('message') or err.get('msg') or err}")

    best = min(data["result"]["path"], key=lambda p: p["info"]["totalTime"])
    info = best["info"]
    return {
        "minutes": info["totalTime"],
        "transfers": max(info.get("busTransitCount", 0) + info.get("subwayTransitCount", 0) - 1, 0),
        "fare": info.get("payment"),
        "legs": [_leg_label(s) for s in best["subPath"] if s["trafficType"] != 3 or s.get("sectionTime")],
    }
