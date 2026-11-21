"""Swagger groups and display order. Tags do not grant access permissions."""
SERVER = '서버 상태'
USER_AUTH = '사용자 등록·인증'
MY_DATA = '내 정보·예약 조회'
LOCATION = '위치·좌석 조회'
SENSOR = 'ESP32 상태 통신'
RESERVATION_READ = '예약 조회'
RESERVATION_WRITE = '예약 등록·변경'
ADMIN_AUTH = '관리자 인증'
ADMIN_RESERVATION = '관리자 예약 관리'
ADMIN_SETTINGS = '관리자 예약 설정'
ADMIN_MAINTENANCE = '관리자 데이터 정리'

OPENAPI_TAGS = [
    {'name': SERVER, 'description': '서버와 데이터베이스 접근 상태를 확인합니다.'},
    {'name': LOCATION, 'description': '공개 층·방·좌석 조회. 현재 예약과 다음 예정 예약, 남은 시간과 마지막 저장 착석 상태를 제공합니다.'},
    {'name': RESERVATION_READ, 'description': '전체·좌석별 예약 목록과 특정 예약을 조회합니다. 로그인 사용자 전용 목록과 구분합니다.'},
    {'name': USER_AUTH, 'description': '프로필 등록, 시연용 학번 로그인과 로그아웃. 실제 학생 신원 인증은 아닙니다.'},
    {'name': MY_DATA, 'description': 'DemoSession으로 내 프로필·IN_USE 예약·독립 이용 좌석 이력을 조회합니다.'},
    {'name': RESERVATION_WRITE, 'description': '예정 예약은 이동·취소, 사용 중 예약은 연장·이동·종료를 허용합니다. 만료·취소·종료 예약은 변경할 수 없고 같은 취소·종료의 반복은 기존 결과를 반환합니다. 임의 시간 수정은 관리자 API에서 처리합니다. DemoSession이 필요하며 변경은 본인 예약만 허용합니다.'},
    {'name': SENSOR, 'description': '인증 없는 ESP32 착석 수신과 예약정보 응답. 장치 키·혼잡도·LED 목표 상태는 제공하지 않습니다.'},
    {'name': ADMIN_AUTH, 'description': '관리자 ID·비밀번호 로그인과 AdminSession 조회·로그아웃. 일반 사용자 세션과 분리됩니다.'},
    {'name': ADMIN_SETTINGS, 'description': '관리자 기본 예약 시간·연장 횟수 조회/수정. 변경은 새 예약부터 적용하고 기존 예약은 생성 당시 정책을 보존합니다.'},
    {'name': ADMIN_RESERVATION, 'description': 'AdminSession으로 가상 예약 등록·시간/상태 수정·영구 삭제. 조회는 공통 예약 조회 경로를 사용합니다.'},
    {'name': ADMIN_MAINTENANCE, 'description': 'AdminSession으로 만료 세션과 보관기간 지난 예약을 정리합니다. 기본은 삭제 없는 대상 건수 미리보기입니다.'},
]
