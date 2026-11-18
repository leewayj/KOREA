import { Button } from './Button'
import './reservation.css'

import { dateFormat, timeFormat } from '../data/reservation'
import './reservation-flow.css'

export default function ReservationPage({ reservation, room, onChange, onExtend, returnOpen, onRequestReturn, now, saving }) {
  const remaining = Math.max(0, reservation.endsAt - now)
  const endingSoon = remaining > 0 && remaining <= 10 * 60000
  const minutes = Math.ceil(remaining / 60000)
  const remainingLabel = `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`
  const duration = reservation.endsAt - reservation.startsAt
  const elapsedAngle = Math.min(360, Math.max(0, (1 - remaining / duration) * 360))

  return (
    <>
      <main className="reservation-content" aria-label="내 예약 정보" inert={returnOpen}>
        <div className="reservation-summary">
          <h2>내 예약 정보</h2>
          {reservation.studentId && <p className="reservation-student">학번 {reservation.studentId}</p>}
          <p>{dateFormat.format(reservation.startsAt).replaceAll('-', '.')} · {room.name}</p>
        </div>
        <section className={`reservation-details${endingSoon ? ' ending-soon' : ''}`} aria-label="좌석과 예약 시간">
          <div className="reservation-status"><span>내 좌석</span><strong role="status">{endingSoon ? '종료 10분 전' : '예약 중'}</strong></div>
          <div className="reservation-seat-time">
            <strong className="reservation-seat-number">{reservation.seat}번</strong>
            <div className="reservation-clock" role="timer" aria-label={`남은 시간 ${Math.floor(minutes / 60)}시간 ${minutes % 60}분`}>
              <img src="/assets/reservation-time-track.svg" alt="" className="reservation-clock-track" />
              <span className={endingSoon ? "reservation-clock-warning" : "reservation-clock-ring"} style={{ maskImage: `conic-gradient(transparent ${elapsedAngle}deg, black ${elapsedAngle}deg)` }}><img src={endingSoon ? "/assets/reservation-time-warning.svg" : "/assets/reservation-time-ring.svg"} alt="" /></span>
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
      <footer className="reservation-actions" inert={returnOpen}>
        <Button variant="neutral" onPress={onRequestReturn} isDisabled={saving || remaining === 0}>좌석 반납</Button>
        <div><Button onPress={onChange} isDisabled={saving || remaining === 0}>좌석 변경</Button><Button variant="neutral" onPress={onExtend} isDisabled={saving || remaining === 0}>예약 연장</Button></div>
      </footer>

    </>
  )
}
