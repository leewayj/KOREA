import { request, list } from '../api.js'
export { apiEnabled as reservationApiEnabled } from '../api.js'
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

export const extendApiReservation = (id) =>
  post('/reservations/' + id + '/extend')

export const endApiReservation = (id) => post('/reservations/' + id + '/end')
