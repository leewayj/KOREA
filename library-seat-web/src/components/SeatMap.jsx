import { reservedSeats, seatRows } from '../data/seats'
import './SeatPage.css'

function makeDesks(serverSeats) {
  if (!serverSeats) {
    return seatRows.map((row) => row.map((start) => [
      start, start + 1, start + 2, start + 5, start + 4, start + 3,
    ]))
  }
  const seats = [...serverSeats].sort((a, b) => Number(a.seat_number) - Number(b.seat_number))
  const desks = []
  for (let index = 0; index < seats.length; index += 6) {
    const group = seats.slice(index, index + 6)
    desks.push([...group.slice(0, 3), ...group.slice(3).reverse()])
  }
  const midpoint = Math.ceil(desks.length / 2)
  return [desks.slice(0, midpoint), desks.slice(midpoint)]
}

export default function SeatMap({ mySeat, selectedSeat, onSelect, changeMode = false, serverSeats }) {
  const deskRows = makeDesks(serverSeats)
  const maxDesks = Math.max(0, ...deskRows.map((row) => row.length))
  const boardWidth = Math.max(588, maxDesks * 78 + Math.max(0, maxDesks - 1) * 24)

  function renderSeat(seat) {
    const number = typeof seat === 'number' ? seat : Number(seat.seat_number)
    const data = typeof seat === 'number'
      ? serverSeats?.find((item) => Number(item.seat_number) === number)
      : seat
    if (serverSeats && !data) return null
    const reserved = serverSeats ? data.reservation_state === 'RESERVED' : reservedSeats.has(number)
    const own = number === mySeat
    const selected = number === selectedSeat
    const status = own ? '내 좌석' : reserved ? '예약됨' : selected ? '선택됨' : '예약 가능'
    return (
      <button key={number} type="button" className={`seat-tile${own || selected ? ' selected' : ''}`}
        disabled={reserved && !own} aria-label={`${number}번 좌석 · ${status}`} aria-pressed={selected || own}
        onClick={(event) => { if (changeMode && own) return; onSelect(number, event.currentTarget) }}>
        {number}
      </button>
    )
  }

  return (
    <section className="seat-map" aria-label={serverSeats ? `${serverSeats.length}석 배치도` : "72석 배치도"}>
      <p className="map-label">창가</p>
      <div className="seat-scroll" tabIndex={0} role="region" aria-label="좌석 배치도 가로 스크롤" aria-describedby="seat-scroll-help">
        <div className="seat-board" style={{ width: boardWidth }}>
          {deskRows.map((row, index) => (
            <div className="seat-row-group" key={index}>
              {index === 1 && <p className="seat-aisle">통로</p>}
              <div className="seat-row">
                {row.map((desk, deskIndex) => (
                  <div className="seat-desk" key={deskIndex}>
                    <div className="seat-column">{desk.slice(0, 3).map(renderSeat)}</div>
                    <div className="seat-column">{desk.slice(3).map(renderSeat)}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <p className="map-label">출입구</p>
    </section>
  )
}
