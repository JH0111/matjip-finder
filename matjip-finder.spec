# PyInstaller 빌드 설정: 폴더형(onedir) 포터블 빌드
#   pyinstaller --noconfirm matjip-finder.spec
# 결과: dist/matjip-finder/  (matjip-finder.exe + _internal/)
# API 키·캐시·지하철 그래프는 넣지 않는다. 첫 실행 때 exe 옆 userdata/ 폴더에 만들어진다.
# 오류를 콘솔로 보고 싶으면 환경변수 MATJIP_CONSOLE=1 로 빌드한다.
import os

CONSOLE = os.environ.get("MATJIP_CONSOLE") == "1"

a = Analysis(
    ["launcher.py"],
    pathex=[],
    datas=[
        ("static", "static"),
        ("data/seoul_metro_interstation.csv", "data"),
        (".env.example", "."),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="matjip-finder",
    console=CONSOLE,
)
coll = COLLECT(exe, a.binaries, a.datas, name="matjip-finder")
