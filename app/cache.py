"""API 응답을 파일로 저장해 같은 요청을 반복 호출하지 않게 하는 간단한 캐시 (무료 쿼터 절약용)."""
import hashlib
import json
import time

from . import config


def _path(namespace: str, key: str):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return config.CACHE_DIR / namespace / f"{digest}.json"


def get(namespace: str, key: str, ttl_seconds: int):
    path = _path(namespace, key)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - entry["saved_at"] > ttl_seconds:
        return None
    return entry["value"]


def put(namespace: str, key: str, value):
    path = _path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"saved_at": time.time(), "value": value}, ensure_ascii=False), encoding="utf-8")
