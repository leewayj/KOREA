from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

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
    def_time: PositiveInteger | None = Field(default=None, description='시작 시각부터의 총 이용시간(초). ends_at과 동시 입력 불가.')
    status: Literal['CONFIRMED', 'ENDED', 'CANCELLED'] | None = None


class AdminReservationCreate(Input):
    seat_id: PositiveInteger
    s_id: Annotated[str, Field(strict=True, min_length=10, max_length=10, pattern=r'^[0-9]{10}$')]
    starts_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]
    ends_at: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)]


class ReservationSettingsEdit(Input):
    default_duration_seconds: PositiveInteger | None = None
    max_extensions: Annotated[int, Field(strict=True, ge=0, le=9223372036854775807)] | None = None


class ReservationSettings(BaseModel):
    id: Literal[1]
    default_duration_seconds: int
    max_extensions: int
    updated_at: int
    updated_by: str | None


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
    def_time: PositiveInteger | None = Field(default=None, description='총 이용시간(초). 생략 또는 null이면 현재 관리자 설정 기본 시간.')


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
    policy_default_duration_seconds: int
    max_extensions: int | None
    extension_count: int
    legacy_extension_policy: bool


class SeatHistory(BaseModel):
    id: int
    s_id: str
    seat_id: int
    used_at: int = Field(description='예약 시작 또는 좌석 이동 시각. UTC Unix 초. 원본 예약 삭제 후에도 유지.')


class NextReservation(BaseModel):
    id: int
    starts_at: int
    ends_at: int


FinalSeatStatus = Literal['AVAILABLE', 'RESERVED_EMPTY', 'RESERVED_OCCUPIED', 'EXPIRING_OCCUPIED', 'EXPIRED_OCCUPIED', 'UNRESERVED_OCCUPIED', 'UNKNOWN']
LedState = Literal['OFF', 'BLUE_ON', 'ORANGE_ON', 'RED_BLINK']


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
    seat_status: FinalSeatStatus
    occupancy_state: OccupancyState | None
    occupied_since: int | None
    occupancy_updated_at: int | None
    server_now: int
    remaining_seconds: int | None
    next_reservation: NextReservation | None
    notice_code: NoticeCode | None
    notice_message: str | None


class RoomIdentity(BaseModel):
    id: int
    name: str


class SeatCounts(BaseModel):
    total: int
    valid: int
    occupied: int
    available: int
    reservedEmpty: int
    unknown: int


class Congestion(BaseModel):
    status: Literal['OK', 'INSUFFICIENT_DATA']
    reason: Literal['NO_SEATS', 'NO_VALID_SEATS', 'LOW_COVERAGE'] | None
    level: Literal['LOW', 'MODERATE', 'HIGH'] | None
    percent: Annotated[int, Field(ge=0, le=100)] | None
    calculatedAt: AwareDatetime


class RoomNextReservation(BaseModel):
    id: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime


class RoomStatusSeat(BaseModel):
    seat_id: int
    seat_number: str
    seat_status: FinalSeatStatus
    reservation_state: Literal['AVAILABLE', 'RESERVED']
    active_reservation_id: int | None
    starts_at: AwareDatetime | None
    ends_at: AwareDatetime | None
    remaining_seconds: int | None
    next_reservation: RoomNextReservation | None
    notice_code: NoticeCode | None
    notice_message: str | None


class RoomStatus(BaseModel):
    room: RoomIdentity
    serverTime: AwareDatetime
    congestion: Congestion
    seatCounts: SeatCounts
    hasSimulatedData: bool
    seats: list[RoomStatusSeat]


class AdminSeat(Seat):
    target_led: LedState
    led_state: LedState | None
    led_state_updated_at: int | None
    device_connected: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class OccupancyUpdate(Input):
    state: Literal['OCCUPIED', 'EMPTY', 'SENSOR_ERROR']
    led_state: LedState | None = None


class DeviceReservationInfo(BaseModel):
    seat_status: FinalSeatStatus
    target_led: LedState
    seat_id: int
    reservation_state: Literal['AVAILABLE', 'RESERVED']
    active_reservation_id: int | None
    starts_at: int | None
    ends_at: int | None
    remaining_seconds: int | None
    next_reservation: NextReservation | None
    server_now: int
