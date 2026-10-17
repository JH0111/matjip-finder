# 로컬에서 포터블 zip 만들기 (GitHub Actions 와 같은 결과물)
#   .\build.ps1                 → dist\matjip-finder-v<버전>-win64.zip
#   .\build.ps1 -OutDir D:\out  → 빌드 산출물을 다른 폴더에 (OneDrive 동기화를 피하고 싶을 때)
param([string]$OutDir = "$PSScriptRoot\dist-build")

# PyInstaller 는 일반 로그도 stderr 로 쓰므로 Stop 으로 두면 PowerShell 5.1 이 오류로 멈춘다. 성공 여부는 종료 코드로 본다.
$env:PYTHONPATH = ""
$envDir = "$env:USERPROFILE\.conda\envs\matjip"
$py = "$envDir\python.exe"
# conda 의 OpenSSL 등 DLL 이 Git(mingw64) 등 PATH 의 다른 버전보다 먼저 잡히도록 한다. (안 하면 _ssl 로드 실패)
$env:PATH = "$envDir;$envDir\Library\bin;$envDir\DLLs;$env:PATH"

Set-Location $PSScriptRoot
$version = (& $py -c "from app.version import VERSION; print(VERSION)").Trim()

& $py -m PyInstaller --noconfirm --log-level WARN --distpath "$OutDir\dist" --workpath "$OutDir\work" matjip-finder.spec 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 실패 (종료 코드 $LASTEXITCODE)" }

$zip = "$OutDir\matjip-finder-v$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$OutDir\dist\matjip-finder" -DestinationPath $zip
Write-Host "완료: $zip"
