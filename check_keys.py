r""".env 에 넣은 API 키가 실제로 동작하는지 확인한다. 키 값은 출력하지 않는다.

실행: PowerShell 에서  $env:PYTHONPATH=""; & "$env:USERPROFILE\.conda\envs\matjip\python.exe" check_keys.py
"""
import asyncio

import httpx

from app import config
from app.clients import kakao, odsay, tmap

# 강남역 → 역삼역 (약 800m)
START = {"lng": 127.027619, "lat": 37.497952}
END = {"lng": 127.036377, "lat": 37.500643}


def mask(key: str) -> str:
    return f"설정됨 ({len(key)}자)" if key else "비어 있음"


async def main():
    print(f"KAKAO_REST_API_KEY: {mask(config.KAKAO_REST_API_KEY)}")
    print(f"KAKAO_JS_KEY:       {mask(config.KAKAO_JS_KEY)}")
    print(f"TMAP_APP_KEY:       {mask(config.TMAP_APP_KEY)}")
    print(f"ODSAY_API_KEY:      {mask(config.ODSAY_API_KEY)}")
    print()
    async with httpx.AsyncClient(timeout=15) as client:
        if config.KAKAO_REST_API_KEY:
            try:
                loc = await kakao.resolve_location(client, "강남역")
                print(f"[카카오] OK - '강남역' → {loc['name']} ({loc['lat']:.5f}, {loc['lng']:.5f})")
            except kakao.KakaoError as e:
                print(f"[카카오] 실패 - {e}")
        if config.TMAP_APP_KEY:
            r = await tmap.walking_time(client, START, END)
            print(f"[TMAP] OK - 강남역→역삼역 도보 {r['minutes']}분, {r['meters']}m" if r else "[TMAP] 실패 - 키 또는 사용 신청 상태를 확인하세요")
        if config.ODSAY_API_KEY:
            # 무료 하루 30건 중 1건을 쓴다.
            try:
                r = await odsay.transit_route(client, START, {"lng": 127.100, "lat": 37.513})  # 잠실 방향 (700m 초과)
                print(f"[ODsay] OK - 강남역→잠실 대중교통 {r['minutes']}분 ({' / '.join(r['legs'])})")
            except odsay.OdsayError as e:
                print(f"[ODsay] 실패 - {e} (키, 등록한 IP/URI를 확인하세요)")


asyncio.run(main())
