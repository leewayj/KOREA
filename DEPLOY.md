# 사용자 페이지와 API 배포

Render의 Docker Web Service에서 사용자 화면과 API를 같은 HTTPS 주소로 제공합니다. 배포 코드는 `deploy/user-api` 브랜치에 준비했습니다. 이 브랜치에 push된 커밋마다 자동 배포합니다.

## GitHub에 업로드

맥 터미널에서 실행합니다.

```bash
cd ~/KOREA-latest
git branch --show-current
git status --short
git add .
git commit -m "feat: 사용자 API 연결과 Render 자동 배포 구성"
git push -u origin deploy/user-api
```

현재 브랜치가 `deploy/user-api`인지 확인합니다. 다른 폴더의 기존 작업은 별도로 관리합니다.

## Render 최초 배포

1. https://dashboard.render.com 에서 GitHub 계정으로 로그인합니다.
2. New → Blueprint를 선택하고 `leewayj/KOREA` 저장소 접근을 연결합니다.
3. Blueprint 브랜치를 `deploy/user-api`, 파일을 `render.yaml`로 선택합니다.
4. `Starter` 서비스와 1GB 영구 디스크 비용을 확인하고 배포합니다. 이 구성은 유료입니다.
5. 배포가 Live가 되면 Render가 표시하는 서비스 URL을 엽니다.
6. 같은 주소의 `/api/health`에 `{"status":"ok"}`가 나오는지 확인합니다.
7. 서로 다른 브라우저에서 서로 다른 테스트 학번으로 등록·로그인하고 예약을 확인합니다.

사용자에게는 서비스 URL을 공유합니다. Swagger는 같은 주소의 `/api/docs`에 있습니다. 관리자 웹 화면은 이 배포 이미지에 포함하지 않았습니다. 관리자 API는 `/api/admin/...`이고 기존 관리자 인증을 요구합니다.

## 다음 수정 자동 반영

```bash
cd ~/KOREA-latest
git switch deploy/user-api
# 코드 수정 후
git add .
git commit -m "수정한 내용"
git push
```

GitHub 웹에서도 `deploy/user-api` 브랜치를 선택하고 파일을 수정·커밋하면 자동 배포됩니다. Render Events에서 빌드·배포 성공을 확인합니다. 맥에만 저장한 수정은 push한 뒤 반영됩니다. 다른 브랜치의 변경은 배포 브랜치에 병합한 뒤 push해야 합니다. 팀의 main에 통합한 후에는 render.yaml의 branch와 Render의 연결 브랜치를 함께 main으로 변경할 수 있습니다.

## 데이터와 실행 방식

- 첫 실행 때 `/var/data/library.db`가 없으면 새 DB와 데모 좌석 8개를 만듭니다. 사용자와 예약은 빈 상태에서 시작합니다.
- 현재 맥의 DB와 계정·예약은 업로드하지 않습니다.
- 재시작과 재배포 때 기존 DB를 검증하고 그대로 사용합니다. 스키마가 바뀌면 백업 후 명시적으로 마이그레이션해야 합니다.
- SQLite이므로 단일 인스턴스·단일 worker로 실행합니다. 디스크가 연결된 재배포에는 잠시 접속 중단이 있을 수 있습니다.
- 관리자 계정이 필요하면 Render Shell에서 `python -m api.admin create --username 원하는ID`를 실행하고 비밀번호를 입력합니다. 기본 계정은 없습니다.
- `KOREA_SEED_DEMO=0`은 처음 만드는 DB를 빈 좌석 구성으로 시작합니다. 이미 만들어진 DB에는 영향을 주지 않습니다.

## 인증 범위

현재 로그인은 학번만 사용하는 시연용 인증입니다. 다른 사람의 학번을 아는 사람이 그 학번으로 로그인할 수 있으므로 팀 시연에는 가상의 학번과 이름을 사용합니다. 실제 학생 대상 운영에는 학교 로그인 또는 비밀번호 등 본인 인증을 추가해야 합니다.

이번 배포 코드에는 본인 예약의 조회·이동·수정·연장·취소·반납에 소유권 검사를 추가했습니다. 전체 예약 목록은 관리자만 조회합니다. API 서버를 배포할 때 이 저장소의 `api`를 사용합니다.

## Docker로 직접 실행

Docker가 설치된 환경에서는 다음과 같이 빌드하고 실행할 수 있습니다.

```bash
docker build -t korea-reservations .
docker run --rm -p 8000:8000 -v korea-data:/var/data korea-reservations
```

http://localhost:8000 에서 사용자 화면을 엽니다. 실제 외부 배포에는 HTTPS를 제공하는 호스팅을 사용합니다.
