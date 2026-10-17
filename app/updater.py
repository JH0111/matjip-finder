"""'지금 업데이트': 새 릴리스 zip 을 받아 풀고, 프로그램이 종료된 뒤 파일을 교체하고 다시 실행한다.

- userdata/ (API 키, 캐시, 지하철 노선망)는 절대 건드리지 않는다.
- 실행 중인 exe 는 스스로 덮어쓸 수 없으므로, 교체는 별도 PowerShell 스크립트가 맡는다.
- zip 으로 실행한 프로그램(FROZEN)에서만 동작한다. 개발 모드에서는 git pull 로 업데이트한다.
"""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import httpx

from . import config

ALLOWED_HOSTS = ("https://github.com/", "https://objects.githubusercontent.com/")
EXE_NAME = "matjip-finder.exe"

# desktop.py 가 '창을 닫고 종료하는 함수'를 넣어 둔다.
request_exit = None

# 업데이트 도우미: 앱 프로세스가 끝나기를 기다린 뒤 userdata 를 빼고 미러링하고, 다시 실행한다.
SCRIPT = r"""
param([int]$AppPid, [string]$Src, [string]$Dst, [string]$Log)
"[$(Get-Date -Format s)] 업데이트 시작: $Src -> $Dst" | Out-File $Log -Append -Encoding utf8
for ($i = 0; $i -lt 60; $i++) {
    if (-not (Get-Process -Id $AppPid -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
}
Get-Process -Id $AppPid -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500
# _internal(라이브러리)은 새 버전과 똑같이 맞추고(예전 파일 삭제), 최상위 파일은 덮어쓰기만 한다.
# userdata 와 사용자가 넣어 둔 다른 파일(예: 읽어주세요.txt)은 건드리지 않는다.
robocopy (Join-Path $Src '_internal') (Join-Path $Dst '_internal') /MIR /R:3 /W:1 /NFL /NDL /NP | Out-File $Log -Append -Encoding utf8
$r1 = $LASTEXITCODE
robocopy $Src $Dst /E /R:3 /W:1 /NFL /NDL /NP /XD _internal userdata matjip-finder.exe.WebView2 | Out-File $Log -Append -Encoding utf8
$r2 = $LASTEXITCODE
"[$(Get-Date -Format s)] robocopy 종료 코드 $r1 / $r2 (8 미만이면 성공)" | Out-File $Log -Append -Encoding utf8
Start-Process (Join-Path $Dst 'matjip-finder.exe')
Remove-Item (Split-Path $Src -Parent) -Recurse -Force -ErrorAction SilentlyContinue
"""


class UpdateError(RuntimeError):
    pass


def available() -> bool:
    return config.FROZEN


async def prepare_and_launch(asset_url: str) -> str:
    """zip 을 받아 풀고 도우미 스크립트를 띄운다. 반환 후 앱이 종료되어야 교체가 진행된다."""
    if not available():
        raise UpdateError("zip 으로 실행한 프로그램에서만 자동 업데이트를 쓸 수 있습니다. (개발 중에는 git pull)")
    if not asset_url or not asset_url.startswith(ALLOWED_HOSTS):
        raise UpdateError("업데이트 파일 주소가 올바르지 않습니다.")

    work = Path(tempfile.mkdtemp(prefix="matjip-update-"))
    zip_path = work / "update.zip"
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", asset_url) as resp:
                if resp.status_code != 200:
                    raise UpdateError(f"업데이트 파일을 받지 못했습니다 (HTTP {resp.status_code}).")
                with zip_path.open("wb") as f:
                    async for chunk in resp.aiter_bytes(1 << 16):
                        f.write(chunk)

        extract = work / "extracted"
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(extract)
        # zip 안의 최상위 폴더(matjip-finder/) 를 찾는다.
        candidates = [p.parent for p in extract.rglob(EXE_NAME)]
        if not candidates:
            raise UpdateError(f"업데이트 파일 안에 {EXE_NAME} 이 없습니다.")
        new_app = candidates[0]
        if (new_app / "userdata").exists():  # 혹시 들어 있어도 내 userdata 를 덮지 않도록
            shutil.rmtree(new_app / "userdata")
        zip_path.unlink()
    except (httpx.HTTPError, zipfile.BadZipFile, OSError) as e:
        shutil.rmtree(work, ignore_errors=True)
        raise UpdateError(f"업데이트 준비 중 오류: {e}") from e

    script = work / "apply_update.ps1"
    script.write_text(SCRIPT, encoding="utf-8-sig")  # BOM: Windows PowerShell 5.1 이 한글을 바로 읽도록
    log = config.USER_DIR / "update.log"
    args = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", str(script),
        "-AppPid", str(os.getpid()), "-Src", str(new_app), "-Dst", str(config.APP_DIR), "-Log", str(log),
    ]
    with log.open("a", encoding="utf-8") as f:
        f.write(f"도우미 실행: {script}\n")
    # DETACHED_PROCESS 를 쓰면 PowerShell 이 콘솔을 못 얻어 바로 끝나므로, 숨은 콘솔(CREATE_NO_WINDOW)로 띄운다.
    # 앱이 Job 에 묶여 있으면 앱이 끝날 때 같이 죽지 않도록 Job 에서 떼어 내고, 허용되지 않으면 그냥 띄운다.
    base_flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, creationflags=base_flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, close_fds=True)
    except OSError:
        subprocess.Popen(args, creationflags=base_flags, close_fds=True)
    return str(new_app)
