# 맛집 반경 검색 로컬 서버 실행: http://localhost:8000
# 시스템 PYTHONPATH 에 예전 Python 폴더가 잡혀 있어서, 이 프로세스에서만 비우고 matjip conda 환경으로 실행한다.
$env:PYTHONPATH = ""
$py = "$env:USERPROFILE\.conda\envs\matjip\python.exe"
Set-Location $PSScriptRoot
& $py -m uvicorn app.main:app --reload --reload-include .env --port 8000
