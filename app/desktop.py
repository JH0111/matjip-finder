"""브라우저 없이 자체 창으로 실행한다: 내부 서버를 백그라운드로 켜고 pywebview 창에 띄운다."""
import socket
import sys
import threading
import time
import urllib.request

import uvicorn
import webview

from . import config
from .main import app
from .version import VERSION

# 카카오 JavaScript 키에 등록한 도메인(http://localhost:8000)과 맞춰야 지도가 뜬다.
PREFERRED_PORT = 8000
STARTUP_TIMEOUT_S = 60

LOADING_HTML = """<!doctype html><meta charset="utf-8">
<body style="font-family:system-ui,'Malgun Gothic',sans-serif;display:grid;place-items:center;height:100vh;margin:0;color:#57534e">
<div style="text-align:center"><div style="font-size:20px;margin-bottom:8px">맛집 반경 검색</div><div id="m">불러오는 중…</div></div>"""

ERROR_HTML = """<!doctype html><meta charset="utf-8">
<body style="font-family:system-ui,'Malgun Gothic',sans-serif;padding:40px;color:#1c1917">
<h2>내부 서버를 시작하지 못했습니다</h2>
<p>프로그램을 닫았다가 다시 실행해 보세요. 계속 안 되면 <code>userdata/app.log</code> 파일 내용을 확인해 주세요.</p>"""


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _pick_port() -> int:
    if _port_free(PREFERRED_PORT):
        return PREFERRED_PORT
    with socket.socket() as s:  # 8000이 쓰이고 있으면 빈 포트 (이 경우 카카오 지도는 뜨지 않는다)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _loopback_sockets(port: int) -> list[socket.socket]:
    """127.0.0.1 과 ::1 양쪽에서 받는다. 'localhost' 가 IPv6 로 먼저 풀리는 PC에서도 바로 연결되게."""
    socks = []
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            s.bind((host, port))
            socks.append(s)
        except OSError:
            if family == socket.AF_INET:
                raise
    return socks


def _wait_until_ready(port: int) -> bool:
    deadline = time.time() + STARTUP_TIMEOUT_S
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def main():
    if config.FROZEN:
        # 콘솔 없는 창 모드에서는 stdout/stderr 가 없으므로 로그 파일로 보낸다.
        log = open(config.USER_DIR / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log

    port = _pick_port()
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", log_config=None))
    threading.Thread(target=server.run, kwargs={"sockets": _loopback_sockets(port)}, daemon=True).start()

    # 서버가 실제로 응답할 때까지 '불러오는 중' 화면을 보여주고, 준비되면 본 화면으로 넘긴다.
    window = webview.create_window(
        f"맛집 반경 검색 v{VERSION}", html=LOADING_HTML, width=1200, height=860, min_size=(800, 600)
    )

    def open_when_ready():
        if _wait_until_ready(port):
            window.load_url(f"http://localhost:{port}/")
        else:
            window.load_html(ERROR_HTML)

    webview.start(open_when_ready)
    server.should_exit = True


if __name__ == "__main__":
    main()
