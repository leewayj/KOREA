# KOREA

## 프로젝트 소개

이 저장소는 팀 프로젝트를 위한 공간입니다.

## 사용자 페이지 API 연결

사용자 페이지는 기존 디자인에서 API의 좌석과 예약을 표시합니다. 첫 화면은 HOME이며, 로그인 버튼 또는 좌석 예약 시 학번 로그인 창이 열립니다. 처음 사용하는 학번은 사용자 등록을 진행합니다.

macOS/Linux에서는 Python 3.11 이상으로 프로젝트 최상위 폴더에서 API를 먼저 실행합니다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r api/requirements/requirements.txt
export KOREA_DB_PATH="$PWD/library.db"
# DB 파일이 없는 첫 실행에만 실행합니다.
.venv/bin/python -m api.db init --demo --output "$KOREA_DB_PATH"
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

기존 DB는 초기화하지 않고 서버를 실행합니다. 이전 스키마의 DB는 먼저 백업하고 `api/API_사용설명서.md`의 마이그레이션 절차를 따릅니다. Windows 명령도 해당 설명서에 있습니다.

위 터미널을 켜두고 새 터미널에서 아래 웹 실행 명령을 사용합니다. 사용자 화면의 `/api` 요청은 Vite가 `http://127.0.0.1:8000`으로 전달합니다. 별도 `.env.local` 없이 개발용 API 설정이 적용됩니다. Swagger는 http://127.0.0.1:8000/docs 입니다.

로그인 세션은 현재 브라우저 탭에 저장되며 만료 시 다시 로그인합니다. 좌석·예약 데이터는 각 팀원이 실행하는 API의 DB에 저장됩니다. 기본 로그인은 학번만 사용하는 시연용 인증입니다.

개발 모드에서 기존 예시 화면을 확인하려면 `?preview=default`를 붙입니다. 정적 빌드를 다른 서버에 올리는 경우 해당 서버에도 `/api` 전달 설정이 필요합니다.

## 사용자·관리자 페이지 함께 실행

Node.js 22.12 이상에서 저장소 최상위 `KOREA` 폴더를 열고 실행합니다.

```sh
npm run install:all
npm run dev
```

`npm run install:all`은 처음 설치하거나 의존성이 변경됐을 때 실행합니다.

- 사용자 페이지: http://127.0.0.1:5173
- 관리자 페이지: http://127.0.0.1:5174
- 같은 터미널에서 Ctrl+C를 누르면 두 서버가 함께 종료됩니다.
- 포트가 사용 중이면 실행에 실패한 서버와 함께 나머지 서버도 종료합니다. 기존에 개별 실행한 서버를 먼저 Ctrl+C로 종료하세요.

개별 실행은 `npm run dev:user`, `npm run dev:admin`을 사용합니다. 각 앱의 폴더에서도 기존 명령으로 실행할 수 있습니다.

## 개발 방식

- 각 팀원은 별도의 Branch에서 작업합니다.
- Pull Request를 통해 변경 사항을 공유합니다.

## 커밋 메시지는 한국어로 작성

- feat - 새로운 기능 추가
  ex. feat: 데이터 저장 기능 추가
- fix - 버그 수정
  ex. fix: 로그인 인증 오류 수정
- refactor - 코드 구조 개선 (동작 유지)
  ex. refactor: 로그인 인증 로직 분리
- docs - 문서 수정
  ex. docs: 로그인 기능 사용법 추가
- chore - 기타 유지보수 작업
  ex. chore: 개발 환경 설정 업데이트
- style - 코드 포맷 수정
- test - 테스트 추가 및 수정
