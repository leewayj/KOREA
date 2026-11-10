import { useEffect, useRef } from 'react'
import { Button } from './Button'
import { reservedSeats, seatRows } from '../data/seats'
import './SeatPage.css'
import './seat-change.css'

export default function SeatPage({ room, menuOpen, selectedSeat, onSelect, mySeat, onReserve, onRefresh, changeMode = false, onContinue }) {
  const dialog = useRef(null)
  const trigger = useRef(null)
  const isSelecting = selectedSeat !== null

  useEffect(() => {
    if (!isSelecting) return
    const panel = dialog.current
    const buttons = panel.querySelectorAll('button')
    buttons[0]?.focus({ preventScroll: true })
    const handleKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onSelect(null)
      }
      if (event.key !== 'Tab') return
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    panel.addEventListener('keydown', handleKey)
    return () => {
      panel.removeEventListener('keydown', handleKey)
      trigger.current?.focus({ preventScroll: true })
    }
  }, [isSelecting, onSelect])

  function renderSeat(number) {
    const reserved = reservedSeats.has(number)
    const own = number === mySeat
    const highlightOwn = own && (!changeMode || !isSelecting)
    const selected = number === selectedSeat
    const status = reserved ? '예약됨' : own ? '내 좌석' : selected ? '선택됨' : '예약 가능'
    return (
      <button key={number} type="button" className={`seat-tile${highlightOwn || selected ? ' selected' : ''}`}
        disabled={reserved} aria-label={`${number}번 좌석 · ${status}`} aria-pressed={selected || own}
        onClick={(event) => { if (changeMode && own) return; trigger.current = event.currentTarget; onSelect(number) }}>
        {number}
      </button>
    )
  }

  return (
    <>
      <main className={`seat-page${changeMode ? ' seat-change-page' : ''}`} aria-label={`${room.name} 좌석 배치도`} inert={menuOpen || isSelecting}>
        {changeMode && !isSelecting && <h2 className="seat-change-title">변경할 좌석을 선택해 주세요</h2>}
        <div className="seat-room-heading">
          <h2>{room.name}</h2>
          <button className="icon-button" aria-label="좌석 현황 새로고침" onClick={onRefresh}>
            <img src={changeMode ? '/assets/reservation-refresh.svg' : '/assets/seat-refresh-v3.svg'} alt="" draggable="false" />
          </button>
        </div>
        <ul className="seat-legend" aria-label="좌석 상태 안내">
          <li><span className="legend-chip" />예약 가능</li>
          <li><span className="legend-chip reserved" />예약됨</li>
          <li><span className="legend-chip own" />내 좌석</li>
        </ul>
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
        {!isSelecting && !changeMode && (
          <div className="seat-guidance" role="status">
            <p>{mySeat ? `${mySeat}번 좌석을 선택했습니다` : '이용할 좌석을 선택해 주세요'}</p>
            <p>{mySeat ? '미리보기 예약이며 실제 예약은 진행되지 않습니다.' : '이미 예약된 좌석은 선택할 수 없습니다.'}</p>
          </div>
        )}
      </main>
      {isSelecting && <div className={`seat-modal-backdrop${changeMode ? ' change-backdrop' : ''}`} aria-hidden="true" onClick={() => onSelect(null)} />}
      <footer className="seat-footer" inert={menuOpen || isSelecting}>
        <p id="seat-scroll-help">{changeMode ? '좌우로 밀어 전체 72석을 확인하세요' : '좌우로 밀어 전체 좌석을 확인하세요.'}</p>
        <Button isDisabled={!changeMode || isSelecting} className={`seat-footer-button${changeMode && !isSelecting ? ' ready' : ''}`} onPress={onContinue}>{changeMode && !isSelecting ? '예약하기' : '좌석을 선택해 주세요'}</Button>
      </footer>
      {isSelecting && (
        <section ref={dialog} className="seat-dialog" role="dialog" aria-modal="true" aria-labelledby="seat-dialog-title" aria-describedby="seat-dialog-description">
          <h2 id="seat-dialog-title">{changeMode ? `${mySeat}번 → ${selectedSeat}번` : `${selectedSeat}번 좌석`}</h2>
          <p id="seat-dialog-description">{changeMode ? '선택한 좌석으로 변경할까요?' : '이 좌석을 선택하시겠어요?'}</p>
          <div className="seat-dialog-actions">
            <Button variant="neutral" onPress={() => onSelect(null)}>취소</Button>
            <Button onPress={() => onReserve(selectedSeat)}>{changeMode ? '확인' : '예약하기'}</Button>
          </div>
        </section>
      )}
    </>
  )
}
