"""서울 지하철(1~8호선) 노선망으로 대중교통 소요시간을 추정한다. API 호출 없이 계산하므로 개수 제한이 없다.

데이터
- data/seoul_metro_interstation.csv : 서울교통공사 역간거리 및 소요시간 (공공누리 1유형, 출처: 서울교통공사)
- data/subway_graph.json            : 위 CSV + 카카오 지하철역 좌표로 만든 그래프 (`python -m app.subway` 로 생성)

추정 방식: 출발지 → (도보) 가까운 역 → 평균 대기 → 지하철 이동(환승 시 환승시간 추가) → 도착역 → (도보) 가게.
버스와 9호선·신분당선 등 1~8호선 외 노선은 포함하지 않는다.
"""
import asyncio
import csv
import heapq
import json
import sys

import httpx

from . import config
from .geo import haversine_m

CSV_PATH = config.RESOURCE_DIR / "data" / "seoul_metro_interstation.csv"
GRAPH_PATH = config.USER_DIR / "data" / "subway_graph.json"

WAIT_MIN = 3  # 첫 열차 평균 대기
TRANSFER_MIN = 4  # 환승 이동 + 대기
ACCESS_WALK_MAX_MIN = 12  # 출발지에서 역까지 걸어갈 수 있는 최대 시간
EGRESS_WALK_MAX_M = 600  # 도착역에서 가게까지 찾아볼 최대 직선거리

# CSV는 노선별로 역이 순서대로 나열되지만 지선은 표시 없이 이어 붙어 있다. 지선 첫 역이 갈라지는 역.
BRANCH_FROM = {("2", "용답"): "성수", ("2", "도림천"): "신도림", ("5", "둔촌동"): "강동"}
# 노선마다 이름이 다른 같은 역 (환승역)
ALIASES = {"이수": "총신대입구"}
# 역명이 바뀌어 카카오에서는 새 이름으로 검색해야 하는 역
KAKAO_QUERY_NAME = {"당고개": "불암산"}


def _base_name(name: str) -> str:
    name = name.strip()
    if name.endswith("역") and len(name) > 2:
        name = name[:-1]
    return ALIASES.get(name, name)


def _minutes(mmss: str) -> float:
    m, s = mmss.split(":")
    return int(m) + int(s) / 60


def _parse_csv():
    """노선별 순서와 역간 소요시간으로 노드·간선을 만든다."""
    with CSV_PATH.open(encoding="cp949", newline="") as f:
        rows = list(csv.DictReader(f))
    nodes, edges = {}, []
    prev_by_line = {}
    for row in rows:
        line, name = row["호선"].strip(), _base_name(row["역명"])
        node = f"{line}:{name}"
        nodes.setdefault(node, {"line": line, "name": name})
        prev = prev_by_line.get(line)
        branch = BRANCH_FROM.get((line, name))
        if branch:
            prev = f"{line}:{branch}"
        if prev and prev != node:
            edges.append([prev, node, round(_minutes(row["소요시간"]), 2)])
        prev_by_line[line] = node
    return nodes, edges


async def _station_coords(names: set[str]) -> dict:
    """카카오 키워드 검색(지하철역 카테고리 SW8)으로 역 좌표를 구한다. 노선별 출구가 달라도 같은 역은 평균을 쓴다."""
    from .clients import kakao

    coords, missing = {}, []
    async with httpx.AsyncClient(timeout=15) as client:
        for name in sorted(names):
            query = KAKAO_QUERY_NAME.get(name, name)
            data = await kakao._get(
                client, "/search/keyword.json", {"query": f"{query}역", "category_group_code": "SW8", "size": 15}
            )
            # '동대문역'이 '동대문역사문화공원역'에 걸리지 않도록 첫 단어가 정확히 같은 것만 쓴다.
            docs = [d for d in data["documents"] if d["place_name"].split()[0] == f"{query}역"]
            if not docs:
                missing.append(name)
                continue
            by_line = {}
            for d in docs:
                for token in d["place_name"].split():
                    if token.endswith("호선"):
                        by_line[token[:-2]] = (float(d["x"]), float(d["y"]))
            coords[name] = {"by_line": by_line, "any": (float(docs[0]["x"]), float(docs[0]["y"]))}
    return coords, missing


def build_graph():
    return asyncio.run(build_graph_async())


async def build_graph_async():
    """CSV + 카카오 역 좌표로 그래프를 만들어 GRAPH_PATH 에 저장한다. 처음 실행 시 설정 화면에서도 호출한다."""
    global _graph
    nodes, edges = _parse_csv()
    coords, missing = await _station_coords({n["name"] for n in nodes.values()})
    for key, n in list(nodes.items()):
        c = coords.get(n["name"])
        if not c:
            del nodes[key]
            continue
        n["lng"], n["lat"] = c["by_line"].get(n["line"], c["any"])
    edges = [e for e in edges if e[0] in nodes and e[1] in nodes]

    # 같은 역 이름의 다른 노선끼리 환승 간선
    by_name = {}
    for key, n in nodes.items():
        by_name.setdefault(n["name"], []).append(key)
    transfers = [[a, b, TRANSFER_MIN] for keys in by_name.values() for a in keys for b in keys if a < b]

    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(
        json.dumps({"nodes": nodes, "edges": edges, "transfers": transfers}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    _graph = None  # 다음 load_graph() 에서 새 파일을 읽는다
    return len(nodes), len(edges), len(transfers), missing


_graph = None


def load_graph():
    global _graph
    if _graph is None:
        if not GRAPH_PATH.exists():
            return None
        data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        adj = {k: [] for k in data["nodes"]}
        for a, b, w in data["edges"]:
            adj[a].append((b, w, False))
            adj[b].append((a, w, False))
        for a, b, w in data["transfers"]:
            adj[a].append((b, w, True))
            adj[b].append((a, w, True))
        _graph = {"nodes": data["nodes"], "adj": adj}
    return _graph


def _walk_min(distance_m: float) -> float:
    return distance_m * config.DETOUR_FACTOR / config.WALK_SPEED_M_PER_MIN


def reachable_stations(origin: dict, max_minutes: float) -> dict:
    """출발지에서 max_minutes 안에 도착할 수 있는 역과 {minutes, board, transfers}."""
    g = load_graph()
    if not g:
        return {}
    dist, info, heap = {}, {}, []
    for key, n in g["nodes"].items():
        walk = _walk_min(haversine_m(origin["lng"], origin["lat"], n["lng"], n["lat"]))
        if walk <= ACCESS_WALK_MAX_MIN:
            t = walk + WAIT_MIN
            if t < dist.get(key, float("inf")):
                dist[key] = t
                info[key] = {"board": key, "access_walk": round(walk), "transfers": 0}
                heapq.heappush(heap, (t, key))
    while heap:
        t, key = heapq.heappop(heap)
        if t > dist[key] or t > max_minutes:
            continue
        for nxt, w, is_transfer in g["adj"][key]:
            nt = t + w
            if nt < dist.get(nxt, float("inf")) and nt <= max_minutes:
                dist[nxt] = nt
                info[nxt] = {**info[key], "transfers": info[key]["transfers"] + (1 if is_transfer else 0)}
                heapq.heappush(heap, (nt, nxt))
    return {
        k: {**g["nodes"][k], "minutes": dist[k], **info[k], "board_name": g["nodes"][info[k]["board"]]["name"]}
        for k in dist
    }


def estimate(stations: dict, place: dict):
    """가게 하나의 지하철 경유 추정치 {'minutes', 'summary', ...} 또는 None (지하철이 도움이 안 되는 경우)."""
    best = None
    for s in stations.values():
        d = haversine_m(s["lng"], s["lat"], place["lng"], place["lat"])
        if d > EGRESS_WALK_MAX_M:
            continue
        total = s["minutes"] + _walk_min(d)
        if best is None or total < best[0]:
            best = (total, s, d)
    if best is None:
        return None
    total, s, d = best
    egress = round(_walk_min(d))
    if s["board_name"] == s["name"]:
        # 출발지 근처 역 바로 앞 가게: 지하철을 타지 않으므로 도보로 처리하도록 None
        return None
    ride = f"{s['board_name']}역 → {s['name']}역"
    if s["transfers"]:
        ride += f" (환승 {s['transfers']}회)"
    return {
        "minutes": round(total),
        "summary": f"도보 {s['access_walk']}분 · 지하철 {ride} · 도보 {egress}분",
        "station": s["name"],
        "estimated": True,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n, e, t, missing = build_graph()
    print(f"역 {n}개, 구간 {e}개, 환승 {t}개 → {GRAPH_PATH}")
    if missing:
        print("좌표를 못 찾은 역:", ", ".join(missing))
