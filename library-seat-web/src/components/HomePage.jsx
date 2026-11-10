import { Button } from './Button'
import { rooms } from '../data/rooms'
import './home.css'

export default function HomePage({ onReserve, onManage, menuOpen, reservation, reservationRoom, onViewReservation }) {
  const primaryAction = reservation ? '좌석 변경' : '좌석 예약'
  return (
    <main className="home-content" aria-label="홈 서비스" inert={menuOpen}>
      <section className="reservation-hero" aria-labelledby="reservation-title">
        <p className="hero-eyebrow">열람실 이용</p>
        <h2 id="reservation-title">열람실 {primaryAction}</h2>
        <Button className="reserve-button" onPress={onReserve} variant="primary">{primaryAction}</Button>
      </section>

      <section className="home-card" aria-labelledby="my-reservation-title">
        <h2 id="my-reservation-title">내 예약</h2>
        {reservation ? <>
          <p className="reservation-empty">{reservationRoom.name} · {reservation.seat}번 좌석</p>
          <Button variant="neutral" size="small" onPress={onViewReservation}>예약 정보 조회</Button>
        </> : <p className="reservation-empty">현재 예약된 좌석이 없어요.</p>}
      </section>

      <section className="home-card" aria-labelledby="favorite-title">
        <div className="favorite-heading">
          <h2 id="favorite-title">선호 좌석</h2>
          <Button className="manage-button" onPress={onManage} variant="neutral" size="small">관리</Button>
        </div>
        <p className="favorite-empty" aria-label="등록된 선호 좌석 없음">—</p>
      </section>

      <section className="home-card congestion-card" aria-labelledby="congestion-title">
        <h2 id="congestion-title">열람실 혼잡도</h2>
        {rooms.map(room => (
          <div className={`congestion-row ${room.tone}`} key={room.id}>
            <span className="congestion-room">{room.name}</span>
            <span className="usage-track" role="meter" aria-label={`${room.name} 좌석 이용률`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={room.usage}>
              <span className="usage-fill" style={{ width: `${room.usage}%` }} />
            </span>
            <span className="congestion-status">{room.congestion} · {room.usage}%</span>
          </div>
        ))}
      </section>
    </main>
  )
}
