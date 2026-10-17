import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 경로
# - RESOURCE_DIR: 프로그램에 같이 들어가는 파일 (화면, 지하철 CSV). PyInstaller 빌드에서는 압축이 풀린 _internal 폴더.
# - USER_DIR: 사용자마다 달라지는 파일 (API 키 .env, 캐시, 지하철 그래프). 빌드에서는 실행 파일 옆 userdata 폴더.
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
    USER_DIR = APP_DIR / "userdata"
else:
    APP_DIR = RESOURCE_DIR = USER_DIR = Path(__file__).resolve().parent.parent
USER_DIR.mkdir(parents=True, exist_ok=True)

ENV_PATH = USER_DIR / ".env"
CACHE_DIR = USER_DIR / ".cache"

KEY_NAMES = ("KAKAO_REST_API_KEY", "KAKAO_JS_KEY", "TMAP_APP_KEY", "ODSAY_API_KEY")
KAKAO_REST_API_KEY = KAKAO_JS_KEY = TMAP_APP_KEY = ODSAY_API_KEY = ""


def reload_keys():
    """ENV_PATH 의 키를 다시 읽어 모듈 변수에 반영한다. (설정 화면에서 저장한 뒤 재시작 없이 적용)"""
    # override=True: 예전(빈) 값이 프로세스 환경에 남아 있어도 .env 의 최신 값을 쓴다.
    load_dotenv(ENV_PATH, override=True)
    module = sys.modules[__name__]
    for name in KEY_NAMES:
        setattr(module, name, os.getenv(name, "").strip())


def save_keys(values: dict):
    """키 값을 ENV_PATH 에 저장한다. 빈 문자열이 아닌 값만 바꾸고, 나머지 줄(주석 등)은 그대로 둔다."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pending = {k: v.strip() for k, v in values.items() if k in KEY_NAMES and v and v.strip()}
    for i, line in enumerate(lines):
        name = line.split("=", 1)[0].strip()
        if name in pending:
            lines[i] = f"{name}={pending.pop(name)}"
    lines += [f"{k}={v}" for k, v in pending.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in KEY_NAMES:
        os.environ.pop(name, None)
    reload_keys()


reload_keys()

# 평균 보행속도(m/분)와 실제 길이 직선보다 길어지는 비율. 도보 후보를 직선거리로 1차 필터링할 때 사용.
WALK_SPEED_M_PER_MIN = 75
DETOUR_FACTOR = 1.3

# 도보 모드에서 한 번 검색할 때 TMAP 실제 경로를 계산할 최대 가게 수 (무료 하루 1,000건 보호용)
MAX_ROUTE_CALLS_PER_SEARCH = 40
