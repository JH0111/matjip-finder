import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, subway, updater, version
from .clients import kakao, odsay
from .search import search

STATIC_DIR = config.RESOURCE_DIR / "static"

app = FastAPI(title="맛집 반경 검색")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def client_config():
    return {
        "version": version.VERSION,
        "kakao_js_key": config.KAKAO_JS_KEY,
        "sources": {
            "kakao": bool(config.KAKAO_REST_API_KEY),
            "tmap": bool(config.TMAP_APP_KEY),
            "odsay": bool(config.ODSAY_API_KEY),
            "subway": subway.load_graph() is not None,
        },
    }


class KeysIn(BaseModel):
    KAKAO_REST_API_KEY: str = ""
    KAKAO_JS_KEY: str = ""
    TMAP_APP_KEY: str = ""
    ODSAY_API_KEY: str = ""


@app.get("/api/settings")
def get_settings():
    """키 값 자체는 돌려주지 않고 설정 여부와 끝 4자리만 보여준다."""
    return {
        "keys": {
            name: {"set": bool(v), "hint": f"…{v[-4:]}" if v else ""}
            for name in config.KEY_NAMES
            for v in [getattr(config, name)]
        },
        "user_dir": str(config.USER_DIR),
    }


@app.post("/api/settings")
def save_settings(keys: KeysIn):
    """빈 칸은 기존 값을 유지한다."""
    config.save_keys(keys.model_dump())
    return get_settings()


@app.post("/api/subway/build")
async def build_subway():
    """처음 실행 시 지하철 노선망을 만든다. 카카오 키가 필요하고 약 280번 호출한다(캐시됨)."""
    try:
        n, e, t, missing = await subway.build_graph_async()
    except kakao.KakaoError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"stations": n, "segments": e, "transfers": t, "missing": missing}


@app.get("/api/version")
async def get_version():
    return {
        "current": version.VERSION,
        "latest": await version.latest_release(),
        "can_auto_update": updater.available(),
    }


@app.post("/api/update")
async def run_update():
    """새 버전 zip 을 받아 준비하고, 응답을 보낸 뒤 앱을 종료한다. 교체와 재실행은 도우미 스크립트가 한다."""
    latest = await version.latest_release(force=True)
    if not latest or not latest["newer"]:
        raise HTTPException(status_code=400, detail="이미 최신 버전입니다.")
    try:
        await updater.prepare_and_launch(latest["asset_url"])
    except updater.UpdateError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if updater.request_exit:
        updater.request_exit()
    return {"version": latest["version"]}


@app.get("/api/search")
async def api_search(
    q: str = Query(..., min_length=1, description="기준 위치 (주소, 역 이름 등)"),
    mode: str = Query("walk", pattern="^(walk|transit)$"),
    minutes: int = Query(15, ge=1, le=90),
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    category: str = Query("", description="쉼표로 구분한 카테고리 (예: 한식,일식)"),
    area: str = Query("", description="쉼표로 구분한 지역 (예: 선릉역 주변)"),
    sort: str = Query("spread", pattern="^(spread|time|distance)$"),
):
    split = lambda s: [x for x in s.split(",") if x]
    try:
        return await search(q, mode, minutes, offset, limit, split(category), split(area), sort)
    except kakao.KakaoError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/route/transit")
async def api_transit_route(
    from_lng: float, from_lat: float, to_lng: float, to_lat: float,
):
    """가게를 클릭했을 때만 ODsay로 정확한 대중교통 경로를 조회한다. (무료 하루 30건, 결과는 저장하지 않음)"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            return await odsay.transit_route(
                client, {"lng": from_lng, "lat": from_lat}, {"lng": to_lng, "lat": to_lat}
            )
    except odsay.OdsayError as e:
        raise HTTPException(status_code=502, detail=str(e))
