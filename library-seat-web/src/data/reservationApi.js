import { request, list } from '../api'
export { apiEnabled as reservationApiEnabled } from '../api'
export async function fetchSeats(signal) {
  return list('/seats', signal)
}

export async function fetchMyReservation(signal) {
  const reservations = await list('/me/reservations', signal)
  return reservations.find(item => ['IN_USE', 'SCHEDULED'].includes(item.effective_status)) || null
}
export const fetchReservation = (id, signal) => request('/reservations/' + encodeURIComponent(id), { signal })
export const fetchSeat = (id, signal) => request('/seats/' + encodeURIComponent(id), { signal })

function post(path, body) {
  return request(path, { method: 'POST', body })
}

export const reserveApiSeat = (seatId, durationSeconds) =>
  post('/reservations', { seat_id: seatId, def_time: durationSeconds })

export const moveApiReservation = (id, seatId) =>
  post('/reservations/' + id + '/move', { target_seat_id: seatId })

export const extendApiReservation = (id, seconds) =>
  post('/reservations/' + id + '/extend', { additional_seconds: seconds })

export const endApiReservation = (id) => post('/reservations/' + id + '/end')
