"""Swagger groups and display order. Tags do not grant access permissions."""
SERVER = '서버 상태'
USER_AUTH = '사용자 등록·인증'
MY_DATA = '내 정보·예약 조회'
LOCATION = '위치·좌석 조회'
RESERVATION_READ = '예약 조회'
RESERVATION_WRITE = '예약 등록·변경'
ADMIN_AUTH = '관리자 인증'
ADMIN_RESERVATION = '관리자 예약 관리'
ADMIN_MAINTENANCE = '관리자 데이터 정리'

OPENAPI_TAGS = [
    {'name': SERVER, 'description': '서버와 데이터베이스 연결 상태 확인.'},
    {'name': USER_AUTH, 'description': '사용자 별도 등록, 학번 로그인, 로그아웃. 실제 학생 본인 여부는 검증하지 않습니다.'},
    {'name': MY_DATA, 'description': 'DemoSession 토큰으로 내 프로필과 내 이용 중 예약을 조회합니다.'},
    {'name': LOCATION, 'description': '로그인 없이 층·방·좌석 위치와 현재·다음 예약, 시간 안내를 조회합니다.'},
    {'name': RESERVATION_READ, 'description': '공개 예약 목록·상세·좌석별 이력 조회.'},
    {'name': RESERVATION_WRITE, 'description': '예약 생성과 이용시간 변경·연장·좌석 이동·취소·종료. 생성은 DemoSession 필수이며 다른 동작의 기존 접근 정책은 유지합니다.'},
    {'name': ADMIN_AUTH, 'description': '관리자 ID·비밀번호 로그인과 AdminSession 확인·로그아웃.'},
    {'name': ADMIN_RESERVATION, 'description': 'AdminSession 토큰으로 사용자·시각 지정 등록, 시각·상태 수정, 개별 영구 삭제.'},
    {'name': ADMIN_MAINTENANCE, 'description': 'AdminSession 토큰으로 만료 예약·세션 정리. 기본은 삭제하지 않는 미리보기입니다.'},
]
