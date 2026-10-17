"""프로그램 버전과 새 버전 확인 (GitHub Releases)."""
import time

import httpx

VERSION = "0.1.1"
# GitHub 저장소 "소유자/이름". 비워 두면 새 버전 확인을 하지 않는다.
GITHUB_REPO = "JH0111/matjip-finder"

_CHECK_INTERVAL = 6 * 3600
_last = {"at": 0.0, "result": None}


def _parse(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in v.lstrip("vV").split("."))


async def latest_release() -> dict | None:
    """{'version', 'url', 'newer'} 또는 확인할 수 없으면 None. 6시간에 한 번만 GitHub에 묻는다."""
    if not GITHUB_REPO:
        return None
    if time.time() - _last["at"] < _CHECK_INTERVAL:
        return _last["result"]
    result = None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
            )
        if resp.status_code == 200:
            data = resp.json()
            tag = data.get("tag_name", "")
            result = {"version": tag.lstrip("vV"), "url": data.get("html_url"), "newer": _parse(tag) > _parse(VERSION)}
    except httpx.HTTPError:
        result = None
    _last.update(at=time.time(), result=result)
    return result
