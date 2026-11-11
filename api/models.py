from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PositiveInteger = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]
Identifier = Annotated[int, Field(gt=0, le=9223372036854775807)]
OccupancyState = Literal['UNKNOWN', 'EMPTY', 'OCCUPIED', 'SENSOR_ERROR']
EffectiveStatus = Literal['SCHEDULED', 'IN_USE', 'ENDED', 'CANCELLED']


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LoginRequest(Input):
    s_id: Annotated[str, Field(strict=True, min_length=10, max_length=10, pattern=r'^[0-9]{10}$')]


ProfileText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=100)]


class UserRegisterRequest(LoginRequest):
    name: ProfileText
    college: ProfileText
    department: ProfileText


class UserRegistration(BaseModel):
    s_id: str
    name: str
    college: str
    department: str
    created_at: int


class AdminLoginRequest(Input):
    username: Annotated[str, Field(strict=True, min_length=3, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')]
    password: Annotated[str, Field(strict=True, min_length=1, max_length=128)]


class AdminIdentity(BaseModel):
    username: str
    created_at: int
    session_expires_at: int


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: Literal['bearer'] = 'bearer'
    expires_in: int
    expires_at: int
    admin: AdminIdentity


class AdminReservationEdit(Input):
    starts_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)] | None = None
    ends_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)] | None = None
    status: Literal['CONFIRMED', 'ENDED', 'CANCELLED'] | None = None


class AdminReservationCreate(Input):
    seat_id: PositiveInteger
    s_id: Annotated[str, Field(strict=True, min_length=10, max_length=10, pattern=r'^[0-9]{10}$')]
    starts_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]
    ends_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]


class ReservationDeleted(BaseModel):
    deleted_reservation_id: int


NoticeCode = Literal['RESERVATION_ENDING_SOON', 'RESERVATION_ENDED', 'RESERVATION_CANCELLED']


class UserIdentity(BaseModel):
    s_id: str
    name: str | None
    college: str | None
    department: str | None
    created_at: int
    session_expires_at: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal['bearer'] = 'bearer'
    expires_in: int
    expires_at: int
    user: UserIdentity


class LogoutResponse(BaseModel):
    message: str


class CleanupRequest(Input):
    dry_run: Annotated[bool, Field(strict=True)] = True
    reservation_retention_days: Annotated[int, Field(strict=True, ge=0, le=36500)] = 30


class CleanupCounts(BaseModel):
    reservations: int
    reservation_moves: int
    reservation_owners: int
    user_sessions: int
    admin_sessions: int


class CleanupResult(BaseModel):
    dry_run: bool
    checked_at: int
    reservation_retention_days: int
    reservation_cutoff_at: int
    matched: CleanupCounts
    deleted: CleanupCounts


class ReservationCreate(Input):
    seat_id: PositiveInteger = Field(description='전역 고유 좌석 ID. 방 안의 표시 번호와 다릅니다.')
    def_time: PositiveInteger | None = Field(default=None, description='총 이용시간(초). 생략 또는 null이면 DB 기본 21600초.')


class ReservationEdit(Input):
    def_time: PositiveInteger = Field(description='예약 시작부터의 총 이용시간(초). 현재 시각부터의 시간이 아닙니다.')


class ReservationExtend(Input):
    additional_seconds: PositiveInteger = Field(description='기존 총 이용시간에 더할 양의 정수 초.')


class ReservationMove(Input):
    target_seat_id: PositiveInteger = Field(description='이동할 좌석의 전역 ID. 예약 ID와 이용시간은 유지합니다.')


class Floor(BaseModel):
    id: int
    code: str
    name: str
    sort_order: int


class Room(BaseModel):
    id: int
    floor_id: int
    code: str
    name: str


class Reservation(BaseModel):
    id: int
    seat_id: int
    confirmed_at: int
    starts_at: int
    def_time: int
    ends_at: int
    status: Literal['CONFIRMED', 'ENDED', 'CANCELLED']
    status_changed_at: int
    effective_status: EffectiveStatus
    server_now: int
    remaining_seconds: int | None
    notice_code: NoticeCode | None
    notice_message: str | None


class NextReservation(BaseModel):
    id: int
    starts_at: int
    ends_at: int


class Seat(BaseModel):
    seat_id: int
    floor_code: str
    floor_name: str
    room_code: str
    room_name: str
    seat_number: str
    active_reservation_id: int | None
    starts_at: int | None
    ends_at: int | None
    reservation_state: Literal['AVAILABLE', 'RESERVED']
    occupancy_state: OccupancyState | None
    occupied_since: int | None
    occupancy_updated_at: int | None
    server_now: int
    remaining_seconds: int | None
    next_reservation: NextReservation | None
    notice_code: NoticeCode | None
    notice_message: str | None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
