import { useEffect, useRef, useState } from 'react'
import { Button } from './Button'
import './reservation.css'

const timeFormat = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' })
const dateFormat = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' })

export default function ReservationPage({ reservation, room, menuOpen, onReturn, onChange, onExtend, returnOpen, onReturnOpenChange }) {
  const returnButton = useRef(null)
  const returnDialog = useRef(null)
  useEffect(() => {
    if (!returnOpen) return
    const panel = returnDialog.current
    const trigger = returnButton.current
    const buttons = panel.querySelectorAll('button')
    buttons[0].focus({ preventScroll: true })
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); onReturnOpenChange(false) }
      if (event.key !== 'Tab') return
      const first = buttons[0], last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    panel.addEventListener('keydown', onKeyDown)
    return () => { panel.removeEventListener('keydown', onKeyDown); trigger?.focus({ preventScroll: true }) }
  }, [returnOpen, onReturnOpenChange])
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const remaining = Math.max(0, reservation.endsAt - now)
  const minutes = Math.ceil(remaining / 60000)
  const remainingLabel = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
  const duration = reservation.endsAt - reservation.startsAt
  const elapsedAngle = Math.min(360, Math.max(0, (1 - remaining / duration) * 360))

  return (
    <>
      <main className="reservation-content" aria-label="내 예약 정보" inert={menuOpen || returnOpen}>
        <div className="reservation-summary">
          <h2>내 예약 정보</h2>
          <p className="reservation-student">학번 {reservation.studentId}</p>
          <p>{dateFormat.format(reservation.startsAt).replaceAll('-', '.')} · {room.name}</p>
        </div>
        <section className="reservation-details" aria-label="좌석과 예약 시간">
          <div className="reservation-status"><span>내 좌석</span><strong>{remaining > 0 ? '예약 중' : '이용 종료'}</strong></div>
          <div className="reservation-seat-time">
            <strong className="reservation-seat-number">{reservation.seat}번</strong>
            <div className="reservation-clock" role="timer" aria-label={`남은 시간 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분`}>
              <img src="/assets/reservation-time-track.svg" alt="" className="reservation-clock-track" />
              <img src="/assets/reservation-time-ring.svg" alt="" className="reservation-clock-ring" style={{ maskImage: `conic-gradient(transparent ${elapsedAngle}deg, black ${elapsedAngle}deg)` }} />
              <span>남은 시간</span><strong>{remainingLabel}</strong><small>시간:분</small>
            </div>
          </div>
          <div className="reservation-time-details">
            <h3>예약 시간</h3>
            <dl>
              <div><dt>시작</dt><dd>{timeFormat.format(reservation.startsAt)}</dd></div>
              <div><dt>종료</dt><dd>{timeFormat.format(reservation.endsAt)}</dd></div>
              <div><dt>총 이용 시간</dt><dd>{duration / 3600000}시간</dd></div>
            </dl>
          </div>
        </section>
      </main>
      <footer className="reservation-actions" inert={menuOpen || returnOpen}>
        <Button ref={returnButton} variant="neutral" onPress={() => onReturnOpenChange(true)}>좌석 반납</Button>
        <div><Button onPress={onChange} isDisabled={remaining === 0}>좌석 변경</Button><Button variant="neutral" onPress={onExtend} isDisabled={remaining === 0}>예약 연장</Button></div>
      </footer>
      {returnOpen && <>
        <div className="seat-modal-backdrop" aria-hidden="true" onClick={() => onReturnOpenChange(false)} />
        <section ref={returnDialog} className="seat-dialog return-dialog" role="dialog" aria-modal="true" aria-labelledby="return-dialog-title" aria-describedby="return-dialog-description">
          <h2 id="return-dialog-title">좌석을 반납하시겠습니까?</h2>
          <p id="return-dialog-description">확인하면 좌석이 반납되고<br />홈 화면으로 이동합니다.</p>
          <div className="seat-dialog-actions"><Button variant="neutral" onPress={() => onReturnOpenChange(false)}>취소</Button><Button onPress={onReturn}>확인</Button></div>
        </section>
      </>}
    </>
  )
}
