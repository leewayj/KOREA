import { rooms } from './rooms'
import { reservedSeats } from './seats'

const storageKey = 'library-seat-preview-reservation'
export const reservationDuration = 2 * 60 * 60 * 1000

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
      || value.endsAt <= value.startsAt || value.endsAt <= Date.now()) return null
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
