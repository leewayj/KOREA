import { reservedSeats, seatRows } from '../data/seats'
import './SeatPage.css'

export default function SeatMap({ mySeat, selectedSeat, onSelect, changeMode = false }) {
  function renderSeat(number) {
    const reserved = reservedSeats.has(number)
    const own = number === mySeat
    const selected = number === selectedSeat
    const status = reserved ? '예약됨' : own ? '내 좌석' : selected ? '선택됨' : '예약 가능'
    return (
      <button key={number} type="button" className={`seat-tile${own || selected ? ' selected' : ''}`}
        disabled={reserved} aria-label={`${number}번 좌석 · ${status}`} aria-pressed={selected || own}
        onClick={(event) => { if (changeMode && own) return; onSelect(number, event.currentTarget) }}>
        {number}
      </button>
    )
  }

  return (
        <section className="seat-map" aria-label="72석 배치도">
          <p className="map-label">창가</p>
          <div className="seat-scroll" tabIndex={0} role="region" aria-label="좌석 배치도 가로 스크롤" aria-describedby="seat-scroll-help">
            <div className="seat-board">
              {seatRows.map((row, index) => (
                <div className="seat-row-group" key={index}>
                  {index === 1 && <p className="seat-aisle">통로</p>}
                  <div className="seat-row">
                    {row.map((start) => (
                      <div className="seat-desk" key={start}>
                        <div className="seat-column">{[start, start + 1, start + 2].map(renderSeat)}</div>
                        <div className="seat-column">{[start + 5, start + 4, start + 3].map(renderSeat)}</div>
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
