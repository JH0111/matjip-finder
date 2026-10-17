"""브라우저 없이 자체 창으로 실행한다: 내부 서버를 백그라운드로 켜고 pywebview 창에 띄운다."""
import socket
import sys
import threading
import time

import uvicorn
import webview

from . import config
from .main import app
from .version import VERSION

# 카카오 JavaScript 키에 등록한 도메인(http://localhost:8000)과 맞춰야 지도가 뜬다.
PREFERRED_PORT = 8000


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _pick_port() -> int:
    if _port_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with socket.socket() as s:  # 8000이 쓰이고 있으면 빈 포트 (이 경우 카카오 지도는 뜨지 않는다)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    if config.FROZEN:
        # 콘솔 없는 창 모드에서는 stdout/stderr 가 없으므로 로그 파일로 보낸다.
        log = open(config.USER_DIR / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    port = _pick_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)

    webview.create_window(f"맛집 반경 검색 v{VERSION}", f"http://localhost:{port}", width=1200, height=860, min_size=(800, 600))
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    main()
