export const MINUTE = 60000;
export const storageKey = "library-seat-admin-demo-v1";
export const rooms = [
  { id: "reading-2", name: "제2열람실 (4F)" },
  { id: "reading-1", name: "제1열람실 (2F)" },
  { id: "focus", name: "집중열람실 (4F)" },
  { id: "holmz", name: "노상일 HOLMZ (4F)" },
];
export const seatNumbers = [66, 67, 68, 69, 70, 71];
export function initialData(now = Date.now()) {
  const t = Math.floor(now / MINUTE) * MINUTE;
  return {
    version: 1,
    settings: { duration: 120, maxExtensions: 2 },
    reservations: rooms.flatMap((room) => [
      {
        id: `${room.id}-66`,
        roomId: room.id,
        seat: 66,
        startsAt: t - 75 * MINUTE,
        endsAt: t + 45 * MINUTE,
        maxExtensions: 2,
      },
      {
        id: `${room.id}-68`,
        roomId: room.id,
        seat: 68,
        startsAt: t - 45 * MINUTE,
        endsAt: t + 75 * MINUTE,
        maxExtensions: 2,
      },
      {
        id: `${room.id}-70`,
        roomId: room.id,
        seat: 70,
        startsAt: t - 130 * MINUTE,
        endsAt: t - 10 * MINUTE,
        maxExtensions: 2,
      },
      {
        id: `${room.id}-66-next`,
        roomId: room.id,
        seat: 66,
        startsAt: t + 75 * MINUTE,
        endsAt: t + 195 * MINUTE,
        maxExtensions: 2,
      },
    ]),
  };
}
export function loadData() {
  try {
    const data = JSON.parse(localStorage.getItem(storageKey));
    if (
      data?.version === 1 &&
      validSettings(data.settings) &&
      Array.isArray(data.reservations) &&
      data.reservations.every(
        (r) =>
          typeof r.id === "string" &&
          rooms.some((x) => x.id === r.roomId) &&
          seatNumbers.includes(r.seat) &&
          Number.isFinite(r.startsAt) &&
          Number.isFinite(r.endsAt) &&
          r.endsAt > r.startsAt,
      )
    )
      return data;
  } catch {
    /* Start a fresh demo when storage is unavailable or invalid. */
  }
  return initialData();
}
export function validSettings(s) {
  return (
    s &&
    Number.isInteger(s.duration) &&
    s.duration > 0 &&
    s.duration <= 1440 &&
    Number.isInteger(s.maxExtensions) &&
    s.maxExtensions >= 0 &&
    s.maxExtensions <= 100
  );
}
export function activeReservation(data, roomId, seat, now) {
  return data.reservations.find(
    (r) =>
      r.roomId === roomId &&
      r.seat === seat &&
      r.startsAt <= now &&
      now < r.endsAt,
  );
}
export function seatsFor(data, roomId, now) {
  const apiSeats = data.rooms?.find((room) => room.id === roomId)?.seats;
  return (apiSeats ?? seatNumbers).map((item) => {
    const number = apiSeats ? item.seat_number : item;
    const reservation = activeReservation(data, roomId, number, now);
    const occupied = apiSeats ? item.occupancy_state === "OCCUPIED" : [66, 70].includes(number);
    const unknown = apiSeats ? !["OCCUPIED", "EMPTY"].includes(item.occupancy_state) : number === 71;
    const expired = data.reservations.some(
      (r) => r.roomId === roomId && r.seat === number && r.endsAt <= now,
    );
    return {
      number,
      reservation,
      occupied,
      unknown,
      attention: unknown || (occupied && !reservation),
      status: unknown
        ? "-"
        : `${reservation ? "예약 중" : expired ? "예약 만료" : "예약 없음"} · ${occupied ? "착석" : "비착석"}`,
    };
  });
}
export function summary(seats) {
  const known = seats.filter((s) => !s.unknown).length;
  const occupied = seats.filter((s) => s.occupied && !s.unknown).length;
  return {
    known,
    occupied,
    unknown: seats.length - known,
    rate: known ? Math.round((occupied / known) * 100) : null,
    reserved: seats.filter((s) => s.reservation).length,
    attention: seats.filter((s) => s.attention).length,
  };
}
export function validateReservation(data, candidate) {
  if (
    data.rooms
      ? !data.rooms.find((room) => room.id === candidate.roomId)?.seats.some((seat) => seat.seat_number === candidate.seat)
      : !rooms.some((r) => r.id === candidate.roomId) || !seatNumbers.includes(candidate.seat)
  )
    return data.rooms ? "현재 열람실의 좌석을 선택하세요." : "관리 좌석 번호 66~71 중 하나를 입력하세요.";
  if (
    !Number.isFinite(candidate.startsAt) ||
    !Number.isFinite(candidate.endsAt)
  )
    return "예약 시작일시와 종료일시를 입력하세요.";
  if (candidate.endsAt <= candidate.startsAt)
    return "종료일시는 시작일시 이후여야 합니다.";
  if (
    data.reservations.some(
      (r) =>
        r.id !== candidate.id &&
        r.roomId === candidate.roomId &&
        r.seat === candidate.seat &&
        r.startsAt < candidate.endsAt &&
        candidate.startsAt < r.endsAt,
    )
  )
    return "같은 좌석의 기존 예약과 시간이 겹칩니다.";
  return "";
}
export function saveReservation(data, candidate) {
  const error = validateReservation(data, candidate);
  if (error) throw new Error(error);
  const existing = data.reservations.find((r) => r.id === candidate.id);
  const reservation = {
    ...candidate,
    id: candidate.id || crypto.randomUUID(),
    maxExtensions: existing?.maxExtensions ?? data.settings.maxExtensions,
  };
  return {
    ...data,
    reservations: [
      ...data.reservations.filter((r) => r.id !== reservation.id),
      reservation,
    ],
  };
}
export const remaining = (r, now) =>
  r ? Math.max(0, Math.ceil((r.endsAt - now) / MINUTE)) : 0;
export const progress = (r, now) =>
  r
    ? Math.max(
        0,
        Math.min(100, ((r.endsAt - now) / (r.endsAt - r.startsAt)) * 100),
      )
    : 0;
// Inputs always represent Korea time, independent of the browser's timezone.
export const inputTime = (t) =>
  Number.isFinite(t)
    ? new Date(t + 9 * 3600000).toISOString().slice(0, 16)
    : "";
export const parseTime = (value) =>
  value ? new Date(`${value}:00+09:00`).getTime() : NaN;
export const dateTime = (t) =>
  inputTime(t).replace("T", " ").replaceAll("-", ".").slice(5);
