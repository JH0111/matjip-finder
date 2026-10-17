# 맛집 반경 검색

기준 위치에서 **도보 / 대중교통 N분 이내**에 있는 음식점을 찾고, 소요시간과 함께 종류·지역별로 골라 볼 수 있게 보여주는 Windows 프로그램입니다. 설치 없이 압축만 풀어서 씁니다.

| 정보 | 소스 | 필수 여부 |
|---|---|---|
| 위치 → 좌표, 반경 내 음식점 목록 | 카카오 로컬 API | 필수 |
| 도보 소요시간 (실제 경로) | TMAP 보행자 경로 API (무료 하루 1,000건) | 선택 (없으면 직선거리 기반 추정) |
| 대중교통 소요시간 (목록) | 서울 지하철 1~8호선 노선망으로 직접 추정 (API 호출 없음) | 대중교통 모드에 필요 |
| 대중교통 정확한 경로 (가게 클릭 시) | ODsay 대중교통 길찾기 API (무료 하루 30건, 결과 저장 안 함) | 선택 |
| 리뷰·평점·영업시간·폐업 여부 | (무료 공식 API 없음) → 카카오맵 링크로 확인 | - |

카카오맵에 검색되는 가게를 그대로 보여주며, 폐업 여부는 따로 확인하지 않습니다.

## 사용 방법 (포터블)

1. [Releases](../../releases)에서 `matjip-finder-vX.Y.Z-win64.zip`을 내려받아 원하는 폴더에 압축을 풉니다.
2. `matjip-finder.exe`를 실행합니다. 브라우저 없이 자체 창으로 열립니다.
3. 처음 실행하면 **API 키 설정** 창이 뜹니다. 각자 발급받은 키를 넣습니다(아래 'API 키 발급').
4. 대중교통 검색을 쓰려면 화면 위의 **지하철 노선망 만들기**를 한 번 누릅니다(약 1분).

- 키, 캐시, 지하철 노선망은 exe 옆 `userdata/` 폴더에만 저장됩니다. 폴더째 USB에 옮겨도 그대로 쓸 수 있습니다.
- **업데이트**: 새 버전이 나오면 화면 위에 안내와 **[지금 업데이트]** 버튼이 뜹니다. 누르면 새 버전을 받아 프로그램 파일만 바꾸고 자동으로 다시 실행합니다. `userdata/`(키, 캐시, 지하철 노선망)는 그대로 남습니다. 기록은 `userdata/update.log`에 남습니다. (v0.1.x는 이 버튼이 없어서 v0.2.0으로 한 번만 직접 바꿔야 합니다.)
- 지도가 안 보이면 카카오 JavaScript 키 설정과 등록 도메인(`http://localhost:8000`)을 확인하세요. 다른 프로그램이 8000번 포트를 쓰고 있어도 지도가 뜨지 않습니다.

## API 키 발급

- **카카오 (필수)**: https://developers.kakao.com → 내 애플리케이션 → 앱 추가 → [카카오맵] 사용 설정 ON → 플랫폼 키의 **REST API 키**. 지도까지 보려면 **JavaScript 키**도 넣고, JavaScript SDK 도메인에 `http://localhost:8000`을 등록합니다.
- **TMAP (선택)**: https://openapi.sk.com → 앱 만들기 → TMAP **Free** 요금제 사용 신청(한도 넘으면 자동 차단, 과금 없음) → 앱키.
- **ODsay (선택)**: https://lab.odsay.com → 애플리케이션 등록 → **Basic**(무료, 개인·학생·5인 이하 스타트업) → 플랫폼 **Server**에 내 공인 IP 등록 → API Key. 집 인터넷의 IP가 바뀌면 ODsay에서 IP를 고쳐야 합니다.

## 무료 한도와 약관

- 카카오 장소 목록은 1일, TMAP 도보 경로는 23시간 동안 캐시합니다. (TMAP 상품약관상 받은 데이터는 24시간 넘게 쓸 수 없습니다.)
- ODsay 결과는 이용약관상 저장하지 않으므로 '정확한 경로'를 누를 때마다 1건씩 씁니다(무료 하루 30건).
- 도보 모드에서 TMAP 실제 경로는 가까운 순으로 최대 40곳만 계산합니다(`app/config.py`의 `MAX_ROUTE_CALLS_PER_SEARCH`). 나머지는 직선거리 기반 추정치입니다.

## 지하철 노선망 데이터

- `data/seoul_metro_interstation.csv`: [서울교통공사 역간거리 및 소요시간](https://data.seoul.go.kr/dataList/OA-12034/S/1/datasetView.do) (출처: 서울교통공사, 공공누리 1유형)
- 역 좌표는 사용자의 카카오 키로 찾아 `userdata/data/subway_graph.json`에 만듭니다. (카카오 API 결과를 배포하지 않기 위해 저장소와 zip에는 넣지 않습니다.)
- 추정 방식: 출발지 → (도보) 가까운 역 → 평균 대기 3분 → 지하철 이동(환승할 때마다 4분 추가) → 도착역 → (도보 600m 이내) 가게.
- 버스와 9호선, 신분당선, 경의중앙선 등 1~8호선 밖의 노선은 아직 포함하지 않습니다. 버스까지 포함한 경로는 가게별 '정확한 경로' 버튼(ODsay)으로 확인합니다.

## 개발

Python 환경은 `matjip` conda 환경(`%USERPROFILE%\.conda\envs\matjip`)을 씁니다.

```powershell
.\run.ps1                 # 개발 서버 (브라우저에서 http://localhost:8000)
python launcher.py        # 창 모드로 실행 (matjip 환경의 python)
.\build.ps1               # 포터블 zip 빌드 → dist-build\matjip-finder-v<버전>-win64.zip
```

개발 모드에서는 키와 캐시를 프로젝트 폴더의 `.env`, `.cache/`, `data/`에 둡니다(모두 git에서 제외).
이 PC는 시스템 `PYTHONPATH`에 예전 Python 폴더가 등록되어 있어서, 스크립트들이 실행할 때만 그 값을 비웁니다.

## 릴리스 (버전 올리기)

1. `app/version.py`의 `VERSION`을 올리고 커밋합니다 (예: `0.2.0`).
2. 같은 이름의 태그를 만들어 푸시합니다.
   ```powershell
   git tag v0.2.0
   git push origin main --tags
   ```
3. GitHub Actions(`.github/workflows/release.yml`)가 Windows에서 zip을 빌드해 Release에 올립니다. 태그와 `VERSION`이 다르면 빌드가 멈춥니다.
