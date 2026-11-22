import { rooms } from './rooms.js'
import { reservedSeats } from './seats.js'

const storageKey = 'library-seat-preview-reservation'
export const reservationDuration = 2 * 60 * 60 * 1000
export const expirationWarningMs = 10 * 60 * 1000

export function createPreviewReservation(roomId, seat) {
  const startsAt = Date.now()
  return { roomId, seat, startsAt, endsAt: startsAt + reservationDuration, studentId: '202600145' }
}

export function readPreviewReservation() {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey))
    if (!value || !rooms.some((room) => room.id === value.roomId)
      || !Number.isInteger(value.seat) || value.seat < 1 || value.seat > 72 || reservedSeats.has(value.seat)
      || !Number.isFinite(value.startsAt) || !Number.isFinite(value.endsAt)
      || value.endsAt <= value.startsAt) return null
    return { ...value, studentId: '202600145' }
  } catch {
    return null
  }
}

export function savePreviewReservation(reservation) {
  try {
    if (reservation) sessionStorage.setItem(storageKey, JSON.stringify(reservation))
    else sessionStorage.removeItem(storageKey)
  } catch {
    // The preview still works in memory when browser storage is unavailable.
  }
}

export const timeFormat = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' })
export const dateFormat = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })

export function formatDuration(durationMs) {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor(totalSeconds / 60) % 60
  const seconds = totalSeconds % 60

  return [
    hours && `${hours}시간`,
    minutes && `${minutes}분`,
    seconds && `${seconds}초`,
  ].filter(Boolean).join(' ') || '0초'
}

export function isReservationActive(reservation, now = Date.now()) {
  return Boolean(reservation && reservation.endsAt > now)
}

export function isReservationEndingSoon(reservation, now) {
  return isReservationActive(reservation, now) && reservation.endsAt - now <= expirationWarningMs
}

export function canChangeSeat(reservation, roomId, seat, now = Date.now()) {
  return isReservationActive(reservation, now) && rooms.some((room) => room.id === roomId)
    && Number.isInteger(seat) && seat >= 1 && seat <= 72
    && !reservedSeats.has(seat) && (roomId !== reservation.roomId || seat !== reservation.seat)
}

export function changeReservationSeat(reservation, roomId, seat, now = Date.now()) {
  return canChangeSeat(reservation, roomId, seat, now) ? { ...reservation, roomId, seat } : reservation
}

export function extendReservation(reservation, now = Date.now()) {
  return isReservationActive(reservation, now) ? { ...reservation, endsAt: reservation.endsAt + reservationDuration } : reservation
}

// Development-only fixtures are kept out of the normal session reservation.
export function createReservationFixture(name, now = Date.now()) {
  const remaining = { ending: 10 * 60000, expired: -1000, expiring: 5000 }[name]
  if (remaining === undefined) return null
  return { roomId: 'reading-2', seat: 14, startsAt: now + remaining - reservationDuration, endsAt: now + remaining, studentId: '202600145' }
}
