import test from 'node:test'
import assert from 'node:assert/strict'
import { canChangeSeat, changeReservationSeat, extendReservation, isReservationActive, createReservationFixture, readPreviewReservation, savePreviewReservation, reservationDuration } from './reservation.js'

const now = Date.UTC(2026, 10, 10, 4, 30)
const reservation = { roomId: 'reading-2', seat: 14, startsAt: now, endsAt: now + reservationDuration, studentId: '202600145' }

test('changing seats preserves the reservation period and original record', () => {
  const changed = changeReservationSeat(reservation, 'reading-2', 10, now)
  assert.deepEqual(changed, { ...reservation, seat: 10 })
  assert.equal(reservation.seat, 14)
})

test('reserved, current and invalid seats or rooms cannot be selected', () => {
  for (const seat of [3, 14, 0, 73, 1.5, NaN]) {
    assert.equal(canChangeSeat(reservation, 'reading-2', seat, now), false)
    assert.equal(changeReservationSeat(reservation, 'reading-2', seat, now), reservation)
  }
  assert.equal(canChangeSeat(reservation, 'unknown-room', 10, now), false)
})

test('changing rooms preserves the existing reservation period and releases the previous room', () => {
  const changed = changeReservationSeat(reservation, 'holmz', 10, now)
  assert.deepEqual(changed, { ...reservation, roomId: 'holmz', seat: 10 })
  assert.equal(reservation.roomId, 'reading-2')
})

test('the same seat number in another room is a different seat', () => {
  assert.equal(canChangeSeat(reservation, 'reading-1', 14, now), true)
  assert.deepEqual(changeReservationSeat(reservation, 'reading-1', 14, now), { ...reservation, roomId: 'reading-1' })
  assert.equal(canChangeSeat(reservation, 'reading-1', 3, now), false)
  assert.equal(canChangeSeat(reservation, 'reading-1', 14, reservation.endsAt), false)
})

test('extending adds two hours to the end, retaining the seat and start', () => {
  const extended = extendReservation(reservation, now + 90 * 60000)
  assert.deepEqual(extended, { ...reservation, endsAt: reservation.endsAt + reservationDuration })
  assert.equal(extended.endsAt - extended.startsAt, 4 * 3600000)
})

test('expiry boundary releases the reservation and prevents changes or extensions', () => {
  assert.equal(isReservationActive(reservation, reservation.endsAt - 1), true)
  assert.equal(isReservationActive(reservation, reservation.endsAt), false)
  assert.equal(extendReservation(reservation, reservation.endsAt), reservation)
  assert.equal(changeReservationSeat(reservation, 'reading-2', 10, reservation.endsAt), reservation)
})

test('expiry preview fixtures retain the full original two-hour duration', () => {
  const ending = createReservationFixture('ending', now)
  assert.equal(ending.endsAt - now, 10 * 60000)
  assert.equal(ending.endsAt - ending.startsAt, reservationDuration)
  assert.equal(isReservationActive(createReservationFixture('expired', now), now), false)
  assert.equal(createReservationFixture('unknown', now), null)
})

test('expired reservation survives reload for the end screen, then return clears it', () => {
  const storage = new Map()
  const original = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage')
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  } })
  try {
    const expired = createReservationFixture('expired', now)
    savePreviewReservation(expired)
    assert.deepEqual(readPreviewReservation(), expired)
    savePreviewReservation({ ...expired, seat: 3 })
    assert.equal(readPreviewReservation(), null)
    savePreviewReservation(null)
    assert.equal(readPreviewReservation(), null)
  } finally {
    if (original) Object.defineProperty(globalThis, 'sessionStorage', original)
    else delete globalThis.sessionStorage
  }
})
