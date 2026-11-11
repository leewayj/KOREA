import { Button } from './Button'
import { dateFormat, timeFormat } from '../data/reservation'
import './reservation-flow.css'

export default function ExpiredReservationPage({ reservation, room, now, onReserve, onConfirm }) {
  const endDay = dateFormat.format(reservation.endsAt)
  const endLabel = endDay === dateFormat.format(now) ? '오늘' : endDay.replaceAll('-', '.')
  return <>
    <main className="reservation-flow-content expired-reservation">
      <h2>예약 이용 시간이 끝났어요.</h2>
      <h3>좌석 예약이 종료되었습니다.</h3>
      <dl className="reservation-info-rows">
        <div><dt>이용 좌석</dt><dd>{room.name.replace(/ \(.*\)$/, '')} · {reservation.seat}번</dd></div>
        <div><dt>종료 시간</dt><dd>{endLabel} {timeFormat.format(reservation.endsAt)}</dd></div>
        <div><dt>현재 상태</dt><dd className="expired-status">예약 종료</dd></div>
      </dl>
      <p className="expired-guidance">계속 이용하려면 좌석을 다시 예약해 주세요.<br />이용을 마쳤다면 자리를 비워 주세요.</p>
    </main>
    <footer className="reservation-actions">
      <Button onPress={onReserve}>새로 예약하기</Button>
      <Button variant="neutral" onPress={onConfirm}>확인</Button>
    </footer>
  </>
}
