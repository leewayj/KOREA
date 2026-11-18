# KOREA API 통합 사용 설명서

작성 기준: 2026-11-11 · API 1.9.0 · Swagger 9개 태그 / 26개 API

실행 기준: `api` 폴더와 `schema.sql`이 있는 프로젝트 루트. 프로젝트 경로·Python·DB·서버 주소는 아래 설정값으로 개인 환경에 맞춘다. Windows PowerShell 명령을 기준으로 설명한다.

## 1. 제공 기능과 사용 흐름

일반 사용자는 사용자 등록 → 학번 로그인 → 좌석 조회 → 예약 생성 → 내 예약 조회 순서로 사용한다. 관리자는 별도의 ID·비밀번호로 로그인하여 사용자를 지정한 예약 등록, 예약 시간·상태 수정, 개별 삭제와 만료 데이터 정리를 수행한다.

예약 조회는 서버 시각·남은 시간·종료 임박 안내를 제공한다. 좌석 조회에는 현재 예약과 가장 가까운 다음 예정 예약이 포함된다. 서버는 기본 1초 주기로 예약시간 상태를 재판정한다.

현재 센서 수신·장치 연결 판정·예약과 착석을 조합한 최종 상태 7종·LED 제어는 구현하지 않았다. 착석 상태는 DB에 저장된 값을 반환하며, `IN_USE`는 예약시간 기준이다. 기존 React 미리보기 화면의 API 연동은 별도 작업이다.

## 2. 개인 환경 설정

서버를 실행하는 사람은 2-1, 이미 실행 중인 API에 요청만 보내는 사람은 2-2를 설정한다. 예제는 이 변수들을 계속 사용하므로 새 PowerShell 창에서는 해당 설정을 다시 실행한다. 프로젝트를 가져오는 위치나 드라이브 이름은 자유롭게 정할 수 있다.

### 2-1. 서버 PC 설정

Python 설치와 프로젝트 준비 후 실행한다. 프로젝트 루트의 전체 경로를 입력하고 나머지 기본값은 필요에 맞춰 수정한다.

```powershell
$projectRoot = (Read-Host '프로젝트 루트의 전체 경로(api 폴더가 있는 위치)').Trim().Trim('"')
Set-Location -LiteralPath $projectRoot
$projectRoot = (Get-Location).Path
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'api/main.py'))) {
    throw '프로젝트 루트 경로를 확인하세요.'
}

$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
$dbPath = Join-Path $projectRoot 'library.db'
$bindAddress = '127.0.0.1'
$apiPort = 8000
$env:KOREA_DB_PATH = $dbPath
$env:KOREA_CLOCK_ENABLED = '1'
```

| 설정값 | 개인 환경에 맞추는 방법 |
|---|---|
| `$projectRoot` | 실제 프로젝트 루트. 공백이 있는 경로도 사용 가능 |
| `$pythonExe` | 사용할 Python 실행 파일. 기본은 프로젝트 내부 `.venv` |
| `$dbPath` | 사용할 DB 파일 전체 경로. 기본은 프로젝트 루트의 `library.db` |
| `$bindAddress` | 같은 PC에서만 쓰면 `127.0.0.1`. 다른 PC 연결을 받을 때는 해당 인터페이스 IP 또는 `0.0.0.0` |
| `$apiPort` | 사용 가능한 서버 포트. 기본 8000 |

기존 가상환경을 사용하려면 `$pythonExe`만 그 실행 파일의 전체 경로로 바꾼다. macOS/Linux의 가상환경 Python 경로는 보통 `.venv/bin/python`이며, 해당 운영체제의 셸에 맞춰 명령을 사용한다. 아래 설치·생성 예제의 `python` 명령도 설치한 Python의 명령명 또는 실행 파일 경로에 맞춘다.

### 2-2. 요청을 보내는 PC 설정

서버 실행과 별도의 PowerShell 창에서 다음을 실행한다. 서버 PC와 다른 PC에서도 주소에 접근할 수 있다면 같은 API 요청을 사용할 수 있다.

```powershell
$baseUrl = (Read-Host 'API 기본 주소(예: http://127.0.0.1:8000)').Trim().TrimEnd('/')
$studentId = Read-Host '사용할 학번(숫자 10자리)'
$adminUsername = Read-Host '관리자 ID(관리자 기능 사용 시 입력)'
```

`$baseUrl`에는 프로토콜·호스트·포트까지만 입력하고 `/docs`는 붙이지 않는다. 같은 PC라면 위 예시 주소를 사용할 수 있지만 포트를 바꿨다면 같이 바꾼다. 다른 PC에서는 서버의 실제 IP나 도메인을 입력한다. `0.0.0.0`은 서버 바인딩 값이며 접속 주소로 사용하지 않는다. API 요청만 하는 PC에는 프로젝트 파일·DB·Python 설치가 필요하지 않다.

| 접속할 주소 | 용도 |
|---|---|
| `$baseUrl/docs` | 브라우저에서 Swagger 열기 |
| `$baseUrl/health` | 연결 확인. 정상 응답 `{"status":"ok"}` |
| `$baseUrl/openapi.json` | 실행 중인 OpenAPI 정의 |

브라우저 주소창에서는 변수명이 아니라 실제 주소를 입력한다. PowerShell에서는 `"$baseUrl/health"`처럼 사용한다. Swagger는 **태그 선택 → API 펼치기 → Try it out → 입력 → Execute** 순서로 실행한다.

## 3. 설치·DB 준비·서버 실행

서버 PC에서 2-1의 설정을 실행한 상태로 진행한다. 새 가상환경이 필요한 경우에만 생성한다.

```powershell
Set-Location -LiteralPath $projectRoot
python -m venv .venv
```

설정한 Python에 실행 패키지를 설치한다.

```powershell
& $pythonExe -m pip install -r (Join-Path $projectRoot 'api/requirements/requirements.txt')
```

기존 환경이 준비되어 있으면 생성을 생략한다. 실행 패키지는 `api/requirements/requirements.txt`, 테스트를 포함한 환경은 같은 폴더의 `requirements-dev.txt`다. 기존 검증 환경의 고정 버전 목록은 `requirements-lock.txt`다. 가상환경 활성화 없이 `$pythonExe`로 직접 실행할 수 있다.

| DB 상태 | 진행 방법 |
|---|---|
| 현재 스키마의 `library.db`가 있음 | 초기화 없이 서버 실행 |
| DB 파일이 없음 | 아래 신규 생성 실행 |
| 호환 가능한 이전 DB가 있음 | 서버 중지 후 아래 마이그레이션 실행 |

신규 DB — `$dbPath` 파일이 없을 때만 실행한다. 다른 폴더를 지정했다면 상위 폴더를 먼저 준비한다.

```powershell
& $pythonExe -m api.db init --demo --output $dbPath
```

`--demo`는 층 2개·방 4개·좌석 8개를 넣는다. 새 DB의 좌석 ID는 1~8이며 사용자·예약·세션·관리자 계정은 비어 있다. 생략하면 스키마만 만든다. 기존 파일을 덮어쓰지 않으므로 파일이 있으면 생성은 실패한다.

이전 DB 업그레이드:

```powershell
$backupPath = "$dbPath.before-upgrade-$(Get-Date -Format 'yyyyMMdd-HHmmss').db"
& $pythonExe -m api.migrations --database $dbPath --backup $backupPath
```

백업 파일은 아직 존재하지 않는 이름을 지정한다. 정상 적용은 `upgraded`, 이미 최신이면 `already_current`와 `backup: null`이다. 임의 구조의 모든 DB를 변환하지는 않으며 부분 변경·다른 구조·기존 다중 활성 예약 등이 있으면 적용을 거부할 수 있다. 기존 DB에 전체 `schema.sql`을 재실행하지 않는다.

본인의 DB 상태에 맞는 준비를 마친 후 서버 실행:

```powershell
Set-Location -LiteralPath $projectRoot
& $pythonExe -m uvicorn api.main:app --host $bindAddress --port $apiPort
```

서버 창은 실행 중 열어 두며 종료는 `Ctrl+C`다. 코드·환경변수를 바꿨다면 재시작한다. 접속이 안 되면 실제 서버 주소·포트와 서버의 바인딩·네트워크 접근 가능 여부를 확인한다. 이 설명서는 개인 DB가 이미 마이그레이션되었다고 가정하지 않는다.

## 4. 인증과 공통 입력 규칙

| 인증 | 사용 대상 | 발급 |
|---|---|---|
| 없음 | 공개 조회·사용자 등록·로그인 및 아래 목록에서 인증 없음으로 표시한 경로 | 해당 없음 |
| `DemoSession` | 사용자 정보·내 예약 조회, 일반 예약 생성, 사용자 로그아웃 | `/auth/login` |
| `AdminSession` | 관리자 정보·예약 관리·데이터 정리·관리자 로그아웃 | `/admin/auth/login` |

두 토큰 모두 HTTP 요청에서는 `Authorization: Bearer <access_token>` 헤더를 사용한다. Swagger 오른쪽 위 **Authorize**에서 맞는 인증 항목에 토큰 **값만** 입력한다. `Bearer ` 접두사·따옴표·전체 응답 JSON을 넣지 않는다.

토큰은 발급 후 1시간 유효하며 조회로 연장되지 않는다. 같은 사용자로 여러 세션을 만들 수 있고 로그아웃은 요청한 토큰 하나만 폐기한다. 서버 재시작 후에도 DB의 유효 세션은 유지된다. DB에는 원문 토큰 대신 해시를 저장한다.

학번 로그인은 비밀번호 없는 시연용 식별이다. 등록된 학번을 아는 다른 사람도 같은 ID로 로그인할 수 있어 실제 학생·본인 확인을 제공하지 않는다. 일반 사용자와 관리자는 별도 계정·세션이다.

시각은 UTC Unix 초 정수, 이용시간은 초다. 날짜 문자열이나 Unix 밀리초를 직접 보내지 않는다. JSON의 숫자 필드에는 문자열 `"600"`, 소수·true 등을 보내지 않는다. 정의되지 않은 본문 필드는 422로 거부한다.

**현재 일반 예약 수정·연장·이동·취소·종료 경로에는 토큰·예약 소유권 검사가 없다.** 생성만 학번 로그인을 요구한다. 태그 이름이 접근 권한을 결정하지는 않으며 아래 표가 실제 인증 설정이다.

## 5. 전체 API 목록

표의 경로를 본인이 설정한 `$baseUrl` 뒤에 붙인다. 예를 들어 PowerShell에서는 `"$baseUrl/seats"`다.

| 태그 | 메서드 | 경로 | 인증 | 입력 | 정상 코드 |
|---|---|---|---|---|---|
| 서버 상태 | GET | `/health` | 없음 | 없음 | 200 |
| 사용자 등록·인증 | POST | `/auth/register` | 없음 | JSON: s_id, name, college, department | 201 |
| 사용자 등록·인증 | POST | `/auth/login` | 없음 | JSON: s_id | 200 |
| 사용자 등록·인증 | POST | `/auth/logout` | DemoSession | 없음 | 200 |
| 내 정보·예약 조회 | GET | `/auth/me` | DemoSession | 없음 | 200 |
| 내 정보·예약 조회 | GET | `/me/reservations` | DemoSession | 쿼리: limit, offset | 200 |
| 위치·좌석 조회 | GET | `/floors` | 없음 | 없음 | 200 |
| 위치·좌석 조회 | GET | `/rooms` | 없음 | 쿼리: floor_id | 200 |
| 위치·좌석 조회 | GET | `/seats` | 없음 | 쿼리: floor_id, room_id, limit, offset | 200 |
| 위치·좌석 조회 | GET | `/seats/{seat_id}` | 없음 | 경로: seat_id | 200 |
| 예약 조회 | GET | `/reservations` | 없음 | 쿼리: seat_id, effective_status, limit, offset | 200 |
| 예약 조회 | GET | `/reservations/{reservation_id}` | 없음 | 경로: reservation_id | 200 |
| 예약 등록·변경 | POST | `/reservations` | DemoSession | JSON: seat_id; 선택: def_time | 201 |
| 예약 등록·변경 | PATCH | `/reservations/{reservation_id}` | 없음 | 경로: reservation_id; JSON: def_time | 200 |
| 예약 등록·변경 | POST | `/reservations/{reservation_id}/extend` | 없음 | 경로: reservation_id; JSON: additional_seconds | 200 |
| 예약 등록·변경 | POST | `/reservations/{reservation_id}/move` | 없음 | 경로: reservation_id; JSON: target_seat_id | 200 |
| 예약 등록·변경 | POST | `/reservations/{reservation_id}/cancel` | 없음 | 경로: reservation_id | 200 |
| 예약 등록·변경 | POST | `/reservations/{reservation_id}/end` | 없음 | 경로: reservation_id | 200 |
| 예약 등록·변경 | POST | `/me/reservations` | DemoSession | JSON: seat_id; 선택: def_time | 201 |
| 관리자 인증 | POST | `/admin/auth/login` | 없음 | JSON: username, password | 200 |
| 관리자 인증 | GET | `/admin/auth/me` | AdminSession | 없음 | 200 |
| 관리자 인증 | POST | `/admin/auth/logout` | AdminSession | 없음 | 200 |
| 관리자 예약 관리 | PATCH | `/admin/reservations/{reservation_id}` | AdminSession | 경로: reservation_id; JSON: starts_at, ends_at, status 중 하나 이상 | 200 |
| 관리자 예약 관리 | DELETE | `/admin/reservations/{reservation_id}` | AdminSession | 경로: reservation_id | 200 |
| 관리자 예약 관리 | POST | `/admin/reservations` | AdminSession | JSON: seat_id, s_id, starts_at, ends_at | 201 |
| 관리자 데이터 정리 | POST | `/admin/maintenance/cleanup` | AdminSession | JSON: 본문 {} 가능; 선택: dry_run, reservation_retention_days | 200 |

조회·동작 성공은 보통 200이며 사용자 등록과 예약 생성은 201이다. 목록은 배열이고 결과가 없으면 `[]`다. 존재하지 않는 필터 대상 ID 자체를 지정하면 404가 될 수 있다.

좌석·예약·내 예약 목록의 `limit`는 기본 100, 1~500이다. `offset`는 기본 0인 건너뛸 개수다. 좌석은 ID 오름차순, 예약은 ID 내림차순이다. 층·방 목록에는 페이지 구분이 없다.

예: `/rooms?floor_id=4`, `/seats?room_id=2&limit=20&offset=0`, `/reservations?effective_status=SCHEDULED&seat_id=1`.

## 6. 사용자 등록·로그인·내 정보

### 6-1. 사용자 등록

`POST /auth/register`:

```json
{
  "s_id": "2026000001",
  "name": "가상사용자",
  "college": "공과대학",
  "department": "컴퓨터학과"
}
```

학번은 ASCII 숫자 10자리 문자열이다. 이름·단과대학·학과는 앞뒤 공백 제거 후 1~100자 문자열이고 모두 필수다. 단과대학·학과의 공식 소속 여부는 검증하지 않는다.

등록 성공은 201이며 입력 정보와 최초 생성 시각 `created_at`을 반환한다. 등록만으로 로그인되지 않는다. 이미 프로필이 있는 학번은 `409 / USER_ALREADY_REGISTERED`이며 기존 값을 덮어쓰지 않는다. 프로필 수정·삭제 API는 없다.

### 6-2. 학번 로그인

`POST /auth/login`:

```json
{"s_id":"2026000001"}
```

새로운 학번은 먼저 등록해야 한다. 미등록 로그인은 `404 / USER_NOT_REGISTERED`이며 사용자를 자동 생성하지 않는다. 응답 구조:

```json
{
  "access_token": "발급된_토큰_값",
  "token_type": "bearer",
  "expires_in": 3600,
  "expires_at": 1800003600,
  "user": {
    "s_id": "2026000001",
    "name": "가상사용자",
    "college": "공과대학",
    "department": "컴퓨터학과",
    "created_at": 1800000000,
    "session_expires_at": 1800003600
  }
}
```

토큰·ID·시각 예시는 실제 응답으로 바꿔 사용한다. `created_at`은 최초 사용자 생성 시각으로 재로그인해도 바뀌지 않는다.

### 6-3. 내 정보와 로그아웃

학번 토큰으로 `GET /auth/me`를 호출하면 위 `user`와 같은 구조를 반환한다. 프로필이 없던 기존 사용자는 로그인·기존 세션을 유지하며 이름·소속이 null일 수 있다. 같은 학번으로 `/auth/register`를 한 번 호출해 보완할 수 있고 기존 예약·세션·생성 시각은 유지한다.

`POST /auth/logout`은 같은 토큰과 **본문 없이** 호출한다. `{}`도 보내지 않는다. 응답은 `{"message":"로그아웃되었습니다."}`다. 폐기한 토큰으로 재조회하거나 다시 로그아웃하면 401이다.

## 7. 좌석 선택과 예약 생성

`GET /floors`, `/rooms`, `/seats`로 실제 ID를 확인한다. `seat_id`는 전체 DB의 고유 ID이며 `seat_number`는 방 안의 표시 번호다. 다른 방에는 같은 표시 번호가 있을 수 있다. 예약에는 반드시 `seat_id`를 사용한다.

학번 토큰으로 `POST /reservations` 또는 `POST /me/reservations`에 같은 본문을 보낸다.

```json
{"seat_id":1,"def_time":600}
```

두 경로는 모두 현재 시각부터 로그인 사용자 명의로 예약을 생성한다. 예약자 학번을 본문으로 받지 않는다. `def_time`은 양의 정수이며 생략·null이면 기본 21600초(6시간)다. 시작·확정 시각은 DB가 설정하고 종료는 `starts_at + def_time`으로 계산한다.

일반 생성에 `starts_at`, `ends_at`, `status`, `s_id` 등을 추가하면 422다. 일반 사용자는 과거·미래 시작을 지정하지 못한다.

같은 학번은 활성 예약을 최대 1개만 가진다. 활성은 `CONFIRMED`이면서 아직 끝나지 않은 예약이며 **`IN_USE`와 `SCHEDULED`를 모두 포함**한다. 로그아웃·재로그인·다른 세션·생성 경로 변경으로 제한을 우회할 수 없다. 취소·조기 종료·자연 만료 후에는 새 예약이 가능하다. 중복 활성은 `409 / ACTIVE_RESERVATION_EXISTS`다.

같은 좌석의 확정 예약 시간 중복도 막는다. 시간 구간은 `[시작, 종료)`이므로 앞 종료와 다음 시작이 같으면 허용한다. 충돌은 `409 / RESERVATION_CONFLICT`다. 현재 빈 좌석이라도 예정 예약과 신청 기간이 겹치면 생성이 거부될 수 있다.

현재 소유자 정보가 없는 이전 예약에는 학번을 임의 지정하지 않았다. 이 예약은 내 예약 목록에 포함되지 않는다.

## 8. 내 예약·예약 응답·시간 안내

학번 토큰으로 `GET /me/reservations`를 호출하면 본인의 **현재 `IN_USE` 예약만** 배열로 반환한다. 없으면 `[]`이며, 예정·종료·취소·타인·소유자 없는 예약은 제외한다. 예정 예약만 있어 목록이 비어도 활성 예약 제한 때문에 추가 생성은 거부될 수 있다.

예약 응답 예시:

```json
{
  "id": 12,
  "seat_id": 1,
  "confirmed_at": 1800000000,
  "starts_at": 1800000000,
  "def_time": 3600,
  "ends_at": 1800003600,
  "status": "CONFIRMED",
  "status_changed_at": 1800000000,
  "effective_status": "IN_USE",
  "server_now": 1800000000,
  "remaining_seconds": 3600,
  "notice_code": null,
  "notice_message": null
}
```

| 필드·값 | 의미 |
|---|---|
| `status` | 저장 상태: `CONFIRMED`, `ENDED`, `CANCELLED` |
| `effective_status` | 현재 시각을 반영한 상태: `SCHEDULED`, `IN_USE`, `ENDED`, `CANCELLED` |
| `server_now` | 이번 조회의 서버 기준 시각 |
| `remaining_seconds` | 예정은 null, 이용 중은 종료-현재, 종료·취소는 0 |
| `notice_code`, `notice_message` | 안내가 없으면 null |

자연 만료해도 저장 `status`는 `CONFIRMED`로 남을 수 있다. 조회에서는 `effective_status=ENDED`로 계산한다. 남은 시간이 1~600초이면 `RESERVATION_ENDING_SOON`, 종료 시각부터 `RESERVATION_ENDED`, 취소는 `RESERVATION_CANCELLED` 안내를 반환한다. 연장 후 600초를 초과하면 임박 안내를 해제한다.

종료된 내 예약은 IN_USE 목록에서 사라진다. 프론트가 종료 안내를 표시하려면 보관한 예약 ID로 `GET /reservations/{reservation_id}`를 재조회한다. 안내는 예약시간 기준이며 실제 착석 지속 여부를 뜻하지 않는다.

좌석 응답은 위치 정보·현재 예약·저장된 착석 상태에 다음 필드를 포함한다.

| 필드 | 의미 |
|---|---|
| `reservation_state` | 현재 유효 예약이 있으면 `RESERVED`, 없으면 `AVAILABLE` |
| `active_reservation_id`, `starts_at`, `ends_at` | 현재 예약 정보. 없으면 null |
| `server_now`, `remaining_seconds` | 공통 조회 시각·현재 예약 남은 시간. 현재 예약 없으면 남은 시간 null |
| `next_reservation` | 가장 가까운 시작 전 확정 예약의 `id`, `starts_at`, `ends_at`. 없으면 null |
| `occupancy_state` | 저장값 `UNKNOWN`, `EMPTY`, `OCCUPIED`, `SENSOR_ERROR` 또는 null |
| `occupied_since`, `occupancy_updated_at` | 저장된 착석 시작·갱신 시각 |
| `notice_code`, `notice_message` | 현재 유효 예약의 안내. 현재 예약 없으면 null |

좌석 목록은 같은 `server_now`로 계산한다. 빈 좌석에 과거 이용자의 종료 안내를 표시하지 않는다. `AVAILABLE`은 실제 비착석을 뜻하지 않으며 현재 API는 착석 상태로 예약·이동을 차단하지 않는다. 사용자·예약 공개 응답에 예약자의 학번·이름·소속을 추가하지 않는다.

## 9. 시간 변경·연장·이동·취소·종료

다음 요청의 예약 ID는 실제 생성·조회한 ID로 바꾼다. JSON 본문이 있는 요청은 `Content-Type: application/json`을 사용한다.

| 동작 | 요청 | 본문 | 효과 |
|---|---|---|---|
| 총 이용시간 교체 | `PATCH /reservations/12` | `{"def_time":1800}` | 최초 시작부터 총 30분으로 변경 |
| 시간 추가 | `POST /reservations/12/extend` | `{"additional_seconds":600}` | 기존 종료에 10분 추가 |
| 좌석 이동 | `POST /reservations/12/move` | `{"target_seat_id":5}` | 시간·예약 ID를 유지하고 좌석만 변경 |
| 취소 | `POST /reservations/12/cancel` | 없음 | `CANCELLED`로 저장 |
| 조기 종료 | `POST /reservations/12/end` | 없음 | `ENDED`로 저장 |

총 이용시간은 현재부터가 아닌 최초 시작 기준이다. 변경 종료는 현재보다 뒤여야 한다. 연장은 반복할 때마다 누적되며 현재 연장 횟수 제한은 없다. 시간 변경·연장은 다른 예약과의 충돌도 검사한다.

좌석 이동은 현재 이용 중인 예약만 가능하고 이동 시점부터 종료까지 대상 좌석의 예약 충돌을 검사한다. 이동은 DB에 이력을 남기며 두 좌석의 착석 상태는 바꾸지 않는다. 같은 좌석으로 반복 이동하면 이력을 추가하지 않는다. 이동 후 좌석 필터는 새 좌석 기준이다.

종료·취소·만료 예약은 일반 경로에서 수정·연장·이동할 수 없다. 취소·조기 종료는 현재 IN_USE 예약에 적용하며 시작 전 예약의 취소는 관리자 수정 경로를 사용한다. 같은 취소 또는 같은 종료의 반복은 저장 결과를 유지하지만 다른 종료 상태로 바꾸면 409다. 요청 시각이 바뀌므로 `server_now` 등 계산 필드는 반복 응답에서도 달라질 수 있다.

## 10. PowerShell로 일반 사용자 흐름 따라 하기

아래 명령은 설정한 서버 DB에 사용자·예약을 저장한다. 서버 실행 후 다른 창에서 2-2의 요청 PC 설정을 준비하고 진행한다. 등록은 최초 한 번만 수행하고 이미 등록된 학번이면 로그인부터 실행한다. 아래 JSON의 고정 ID·시각은 형식 설명용 예시이며 실행할 때는 개인 설정값과 실제 조회한 ID를 사용한다.

```powershell
$registrationBody = @{
    s_id = $studentId
    name = (Read-Host '등록할 이름')
    college = (Read-Host '단과대학')
    department = (Read-Host '학과')
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/register" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($registrationBody))
```

로그인·조회·예약:

```powershell
$userLoginBody = @{ s_id = $studentId } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/login" -ContentType 'application/json' -Body $userLoginBody
$userHeaders = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "$baseUrl/auth/me" -Headers $userHeaders

$myBookings = @(Invoke-RestMethod "$baseUrl/me/reservations" -Headers $userHeaders)
if ($myBookings.Count -gt 0) {
    $booking = $myBookings[0]
} else {
    $seats = @(Invoke-RestMethod "$baseUrl/seats?limit=500")
    $freeSeat = $seats | Where-Object { $_.reservation_state -eq 'AVAILABLE' } | Select-Object -First 1
    if ($null -eq $freeSeat) { throw '예약 가능한 좌석이 없습니다.' }
    $createBody = @{ seat_id=[long]$freeSeat.seat_id; def_time=600 } | ConvertTo-Json
    $booking = Invoke-RestMethod -Method Post -Uri "$baseUrl/reservations" -Headers $userHeaders -ContentType 'application/json' -Body $createBody
}
$bookingId = $booking.id
Invoke-RestMethod "$baseUrl/reservations/$bookingId"
Invoke-RestMethod "$baseUrl/seats/$($booking.seat_id)"
```

내 목록이 비어도 예정 예약이 있으면 새 생성은 409다. 조회 이후 다른 사용자가 같은 좌석을 예약했거나 예정 예약과 시간이 겹쳐도 거부될 수 있다. 전체 좌석이 500개를 넘으면 offset으로 추가 조회한다.

필요한 동작만 선택해 실행한다.

```powershell
Invoke-RestMethod -Method Post -Uri "$baseUrl/reservations/$bookingId/extend" -Headers $userHeaders -ContentType 'application/json' -Body '{"additional_seconds":600}'
Invoke-RestMethod -Method Patch -Uri "$baseUrl/reservations/$bookingId" -Headers $userHeaders -ContentType 'application/json' -Body '{"def_time":1800}'
# 예약 취소 또는 조기 종료 중 필요한 하나를 선택
Invoke-RestMethod -Method Post -Uri "$baseUrl/reservations/$bookingId/cancel" -Headers $userHeaders
# Invoke-RestMethod -Method Post -Uri "$baseUrl/reservations/$bookingId/end" -Headers $userHeaders
Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/logout" -Headers $userHeaders
```

## 11. 관리자 계정·로그인

관리자는 서버 PC에서 별도 생성한다. 공통 기본 계정·비밀번호나 관리자 가입 API는 없다.

```powershell
Set-Location -LiteralPath $projectRoot
$adminUsername = Read-Host '생성할 관리자 ID'
& $pythonExe -m api.admin create --username $adminUsername --database $dbPath
```

서버 PC에서 2-1 설정과 같은 Python·DB를 지정하여 실행한다. 새 창이면 해당 설정을 다시 준비한다. 비밀번호는 프롬프트에서 두 번 입력한다. ID는 영문·숫자·밑줄·하이픈 3~32자, 비밀번호는 8~128자다. 같은 ID를 생성하면 기존 비밀번호를 변경하지 않고 실패한다. 계정을 만든 DB와 서버가 사용하는 DB가 같아야 한다. 비밀번호는 salt를 포함한 PBKDF2-HMAC-SHA256 해시로 저장한다.

관리자 로그인·확인:

요청 PC에서 2-2의 `$baseUrl`, `$adminUsername`을 설정한 상태로 실행한다.

```powershell
$credential = Get-Credential -UserName $adminUsername -Message '관리자 로그인'
$adminLoginBody = @{ username=$credential.UserName; password=$credential.GetNetworkCredential().Password } | ConvertTo-Json
$adminLogin = Invoke-RestMethod -Method Post -Uri "$baseUrl/admin/auth/login" -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($adminLoginBody))
$adminHeaders = @{ Authorization = "Bearer $($adminLogin.access_token)" }
Invoke-RestMethod "$baseUrl/admin/auth/me" -Headers $adminHeaders
```

관리자 응답은 `access_token`, `token_type`, `expires_in`, `expires_at`, `admin`이다. `admin`은 `username`, `created_at`, `session_expires_at`을 포함한다. 잘못된 ID·비밀번호는 `401 / INVALID_CREDENTIALS`다. 일반 학번 토큰으로 관리자 경로를 호출하면 403이다. 로그아웃은 `POST /admin/auth/logout`에 관리자 헤더와 본문 없이 요청한다.

## 12. 관리자 예약 등록·수정·삭제

### 직접 등록

`POST /admin/reservations`, 관리자 토큰 필요:

```json
{"seat_id":1,"s_id":"2026000002","starts_at":1800003600,"ends_at":1800007200}
```

좌석·사용자는 미리 존재해야 한다. 예시 학번과 시각을 실제 값으로 바꾼다. 시작·종료는 0 이상인 64비트 정수이고 시작 < 종료여야 한다. 미래 예정 예약·과거 기록을 등록할 수 있다. 상태는 `CONFIRMED`, 확정 시각은 등록 당시 현재 시각이며 `def_time=종료-시작`이다. 같은 좌석 시간 중복과 사용자별 활성 1개 제한은 관리자에게도 적용한다. 과거 만료 기록은 활성 개수에 포함하지 않는다.

한국 시각을 변환하는 PowerShell 예시:

```powershell
$startAt = [DateTimeOffset]::Parse((Read-Host '시작 시각(예: 2030-01-01T10:00:00+09:00)')).ToUnixTimeSeconds()
$endAt = [DateTimeOffset]::Parse((Read-Host '종료 시각(UTC 오프셋 포함)')).ToUnixTimeSeconds()
```

### 시각·상태 수정

`PATCH /admin/reservations/{reservation_id}`에 `starts_at`, `ends_at`, `status` 중 하나 이상을 보낸다. 생략한 값은 유지하고 null·빈 객체·추가 필드는 거부한다. 저장 상태는 `CONFIRMED`, `ENDED`, `CANCELLED`만 입력한다. `SCHEDULED`, `IN_USE`는 계산 결과다.

관리자는 만료·취소·종료 예약도 편집·재확정할 수 있지만 다른 예약 시간과의 충돌 및 사용자 활성 제한을 지켜야 한다. 시작 전 예약을 ENDED로 지정할 수 없다. 이동 이력이 있으면 새 시작은 마지막 이동 시각 이후일 수 없고 새 종료는 마지막 이동 시각보다 뒤여야 한다. 예약 ID·좌석 ID·확정 시각은 바꾸지 않는다.

### 개별 영구 삭제

`DELETE /admin/reservations/{reservation_id}`를 관리자 헤더와 **본문 없이** 호출한다. 성공은 `{"deleted_reservation_id":12}`, 없는 예약·재삭제는 404다. 예약·이동 이력·소유자 연결·시간 판정 캐시를 같이 삭제하며 사용자·좌석·착석 상태는 유지한다. 복원 API는 없다.

현재 SQLite `INTEGER PRIMARY KEY` 특성상 가장 큰 ID를 삭제하면 새 예약에서 재사용될 수 있다. 삭제 후 기존 목록·선택 정보를 다시 조회한다.

## 13. 만료 예약·세션 정리

관리자 토큰으로 `POST /admin/maintenance/cleanup`에 `{}`를 보내면 기본 **미리보기**다. 예약 보관기간 기본값은 30일이며 `matched`는 대상 건수, `deleted`는 실제 삭제 건수다. 미리보기에서는 deleted가 모두 0이다.

실제 삭제할 때만 다음을 보낸다.

```json
{"dry_run":false,"reservation_retention_days":30}
```

| 대상 | 삭제 기준 |
|---|---|
| 자연 만료 예약 | `CONFIRMED`이고 종료 시각이 현재-보관기간 이하 |
| 종료·취소 예약 | 상태 변경 시각이 현재-보관기간 이하 |
| 사용자·관리자 세션 | 만료 시각이 현재 이하 |
| 이동 이력·소유자 연결·시간 캐시 | 삭제한 예약의 연결 행만 함께 삭제 |

보관기간은 0~36500 정수이며 0일이면 현재까지 만료·종료·취소된 예약이 즉시 대상이다. 세션은 예약 보관기간과 무관하게 만료 즉시 대상이다. 사용자·프로필·관리자 계정·유효/예정 예약·유효 세션·좌석은 유지한다.

삭제는 한 트랜잭션이고 실패하면 전체 롤백한다. 대상이 없으면 0건으로 정상 응답한다. 미리보기와 실제 실행 사이 데이터가 바뀌면 건수도 달라질 수 있다. 응답에는 `dry_run`, `checked_at`, `reservation_retention_days`, `reservation_cutoff_at`, `matched`, `deleted`가 포함된다. 두 건수 객체의 키는 `reservations`, `reservation_moves`, `reservation_owners`, `user_sessions`, `admin_sessions`다.

실제 삭제 후 예약 상세는 404다. 정리 API는 백업·복원·주기적 자동 실행·VACUUM을 수행하지 않는다. 현재 로그인 API에서도 해당 종류의 만료 세션을 정리하므로 대상 건수가 0일 수 있다.

## 14. 서버 시각 판정·프론트 연결 설정

서버 PC에서는 2-1의 `$dbPath`를 `KOREA_DB_PATH`로 지정한다. 미설정 시 기본 DB는 현재 작업 폴더와 관계없이 프로젝트 루트의 `library.db`다. 다른 DB를 쓸 때는 `$dbPath`와 환경변수를 함께 바꾼다.

```powershell
$dbPath = Read-Host '사용할 DB 파일의 전체 경로'
$env:KOREA_DB_PATH = $dbPath
```

다른 Origin의 프론트에서 사용할 때만 다음을 설정한다. 프로토콜·호스트·포트까지 입력하고 경로는 붙이지 않는다. 여러 주소는 쉼표로 구분한다.

```powershell
$frontendOrigins = Read-Host '허용할 프론트 Origin(쉼표 구분, 없으면 Enter)'
if ([string]::IsNullOrWhiteSpace($frontendOrigins)) {
    Remove-Item Env:KOREA_CORS_ORIGINS -ErrorAction SilentlyContinue
} else {
    $env:KOREA_CORS_ORIGINS = $frontendOrigins
}
```

다른 DB 파일이 없으면 초기화 도구로 최초 한 번 생성해야 하며 서버가 자동 생성하지 않는다. `--database`·`--output`을 생략한 관리 명령도 기본 DB 환경변수를 따른다. CORS는 지정한 Origin에 GET·POST·PATCH·DELETE와 `Content-Type`, `Authorization`을 허용한다. 미설정 시 CORS 미들웨어를 추가하지 않는다.

시간 작업은 기본 1초 간격으로 계산 캐시를 갱신한다. 여러 프로세스는 DB의 3초 임대로 실행 주체를 하나로 제한한다. DB 잠금·부하로 지연될 수 있으며 조회는 캐시와 별도로 요청 시각을 다시 계산한다. API 쓰기 작업에서도 캐시를 갱신한다. 원본 예약 상태를 매초 덮어쓰지 않는다.

서버 시작 전에 `$env:KOREA_CLOCK_ENABLED='0'`이면 주기 작업을 끈다. 조회 시 시간 계산은 유지한다. 기본 DB·주기 작업 설정을 복원하려면 해당 환경변수를 제거하고 재시작한다.

프론트는 예를 들어 2초마다 조회하고 `server_now`·`ends_at`으로 남은 시간을 표시·보정한다. 서버의 주기 작업만으로 브라우저 화면이 자동 갱신되지는 않는다. 오류가 나면 이전 값을 최신 정상 상태처럼 표시하지 않도록 처리한다.

## 15. 오류와 실행 문제

공통 오류 형식:

```json
{"error":{"code":"ACTIVE_RESERVATION_EXISTS","message":"이미 활성 예약이 있습니다. 기존 예약을 종료하거나 취소한 뒤 다시 예약하세요."}}
```

| HTTP | 대표 코드 | 조치 |
|---|---|---|
| 401 | `AUTH_REQUIRED`, `INVALID_SESSION` | 토큰 등록 상태·만료·로그아웃 여부 확인, 재로그인 |
| 401 | `INVALID_CREDENTIALS` | 관리자 ID·비밀번호 확인 |
| 403 | `ADMIN_REQUIRED` | 학번 토큰 대신 관리자 토큰 사용 |
| 404 | `USER_NOT_REGISTERED` | 사용자 등록 또는 관리자 대상 학번 확인 |
| 404 | `NOT_FOUND`, `RESERVATION_NOT_FOUND`, `HTTP_ERROR` | 실제 조회한 ID와 경로 확인 |
| 409 | `USER_ALREADY_REGISTERED` | 기존 프로필은 덮어쓰지 않음. 로그인 진행 |
| 409 | `ACTIVE_RESERVATION_EXISTS` | 예정 포함 기존 활성 예약 확인 |
| 409 | `RESERVATION_CONFLICT` | 다른 좌석·겹치지 않는 시간 선택 |
| 409 | `RESERVATION_CLOSED`, `RESERVATION_EXPIRED` | 종료·취소·만료 예약의 일반 변경 불가 |
| 422 | `VALIDATION_ERROR`, `INVALID_DURATION`, `INVALID_STATUS`, `CONSTRAINT_VIOLATION` | 입력 필드·자료형·시간·상태·이동 이력 제약 확인 |
| 503 | `DATABASE_BUSY` | 잠시 후 재시도. `Retry-After: 1` 제공 |
| 500 | `DATABASE_ERROR`, `INTERNAL_ERROR` | 서버 로그에서 원인 확인 |

Swagger의 `INVALID_SESSION`은 새 로그인 응답의 토큰 값만 올바른 DemoSession/AdminSession에 다시 입력해 확인한다. 로그아웃한 토큰의 재사용은 실패하는 것이 정상이다.

패키지·api 모듈을 찾지 못하면 `$projectRoot`에서 설정한 `$pythonExe`로 실행했는지 확인한다. 포트가 사용 중이면 기존 서버를 종료하거나 `$apiPort`를 바꾸고, 요청 PC의 `$baseUrl`에도 같은 포트를 사용한다. DB 호환 오류는 경로·환경변수·마이그레이션을 확인한다. 기존 DB를 삭제하거나 초기화해서 해결하지 않는다.
