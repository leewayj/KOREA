import test from "node:test";
import assert from "node:assert/strict";
import {
  initialData,
  MINUTE,
  seatsFor,
  summary,
  saveReservation,
  validateReservation,
  inputTime,
  parseTime,
  validSettings,
} from "./store.js";
const now = Date.UTC(2026, 10, 17, 6, 15);
test("혼잡도는 미확인 좌석을 제외하고 실제 착석을 집계한다", () => {
  const s = summary(seatsFor(initialData(now), "reading-2", now));
  assert.deepEqual(s, {
    known: 5,
    occupied: 2,
    unknown: 1,
    rate: 40,
    reserved: 2,
    attention: 2,
  });
  assert.equal(summary([{ unknown: true, occupied: false }]).rate, null);
});
test("동일 좌석 예약 중복과 시간 역전을 차단하고 경계에 붙은 예약을 허용한다", () => {
  const d = initialData(now),
    r = d.reservations[0];
  const candidate = {
    roomId: r.roomId,
    seat: r.seat,
    startsAt: r.endsAt,
    endsAt: r.endsAt + 30 * MINUTE,
  };
  assert.equal(validateReservation(d, candidate), "");
  assert.match(
    validateReservation(d, { ...candidate, startsAt: r.endsAt - 1 }),
    /겹칩니다/,
  );
  assert.match(
    validateReservation(d, { ...candidate, endsAt: candidate.startsAt }),
    /이후/,
  );
  assert.match(validateReservation(d, { ...candidate, seat: 72 }), /66~71/);
});
test("수정 시 자기 예약은 제외하되 다음 예약과 중복을 차단한다", () => {
  const d = initialData(now),
    r = d.reservations[0];
  assert.equal(
    validateReservation(d, { ...r, endsAt: r.endsAt + 15 * MINUTE }),
    "",
  );
  assert.match(
    validateReservation(d, { ...r, endsAt: r.endsAt + 31 * MINUTE }),
    /겹칩니다/,
  );
});
test("설정 변경은 기존 예약을 유지하고 새 예약에 적용한다", () => {
  const d = initialData(now);
  d.settings = { duration: 60, maxExtensions: 5 };
  const next = saveReservation(d, {
    roomId: "reading-2",
    seat: 67,
    startsAt: now,
    endsAt: now + 60 * MINUTE,
  });
  assert.equal(next.reservations[0].maxExtensions, 2);
  assert.equal(next.reservations.at(-1).maxExtensions, 5);
  assert.equal(d.reservations.length + 1, next.reservations.length);
});
test("예약 만료 시 예약 수와 확인 필요 상태가 자동 갱신된다", () => {
  const d = initialData(now);
  const s = summary(seatsFor(d, "reading-2", now + 46 * MINUTE));
  assert.equal(s.reserved, 1);
  assert.equal(s.attention, 3);
});
test("입력 날짜는 브라우저 시간대와 관계없이 한국 표준시로 왕복한다", () => {
  assert.equal(inputTime(now), "2026-11-17T15:15");
  assert.equal(parseTime("2026-11-17T15:15"), now);
  assert.ok(Number.isNaN(parseTime("")));
});
test("운영 설정은 양의 예약시간과 0 이상의 정수 연장횟수만 허용한다", () => {
  assert.equal(validSettings({ duration: 120, maxExtensions: 0 }), true);
  assert.equal(validSettings({ duration: 0, maxExtensions: 2 }), false);
  assert.equal(validSettings({ duration: 120, maxExtensions: 1.5 }), false);
});
