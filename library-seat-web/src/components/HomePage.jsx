import { Button } from './Button'
import { timeFormat } from '../data/reservation'
import { previewStudent } from '../data/profile'
import { session } from '../api'
import './home.css'

function ActiveReservationCard({ reservation, room, now, onViewReservation }) {
  const remaining = Math.max(0, reservation.endsAt - now)
  const remainingMinutes = Math.ceil(remaining / 60000)
  const remainingPercent = Math.min(100, remaining / (reservation.endsAt - reservation.startsAt) * 100)
  const remainingLabel = `${Math.floor(remainingMinutes / 60)}시간 ${remainingMinutes % 60}분 남음`

  return (
    <section className="home-card home-reservation-active" aria-labelledby="my-reservation-title">
      <div className="home-reservation-heading">
        <div className="home-reservation-title">
          <h2 id="my-reservation-title">내 예약</h2>
          <span className="home-reservation-badge">이용 중</span>
        </div>
        <Button className="home-reservation-details" variant="neutral" size="small" aria-describedby="home-reservation-seat" onPress={onViewReservation}>
          자세히 보기
          <img src="/assets/v02-chevron.svg" alt="" />
        </Button>
      </div>
      <div className="home-reservation-info">
        <p id="home-reservation-seat" className="home-reservation-seat">{room.name} · {reservation.seat}번 좌석</p>
        <time dateTime={new Date(reservation.endsAt).toISOString()}>{timeFormat.format(reservation.endsAt)} 종료</time>
      </div>
      <div className="usage-track home-reservation-progress" role="meter" aria-label="남은 예약 시간" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remainingPercent)} aria-valuetext={remainingLabel}>
        <span className="usage-fill" style={{ width: `${remainingPercent}%` }} />
      </div>
    </section>
  )
}

export default function HomePage({ rooms, apiMode, onReserve, onManage, reservation, reservationRoom, onViewReservation, now, returnOpen, onRequestReturn }) {
  const user = apiMode ? session()?.user : null
  const student = user ? { studentId: user.s_id, college: user.college, department: user.department, year: null } : apiMode ? { studentId: '로그인 필요', college: '—', department: '—', year: null } : previewStudent
  return (
    <main className="home-content" aria-label="홈 서비스" inert={returnOpen}>
      <section className="profile-card" aria-labelledby="profile-title">
        <h2 id="profile-title">내정보</h2>
        <div className="profile-overview">
          <div className="profile-photo-placeholder" role="img" aria-label="프로필 사진 미등록" />
          <dl className="profile-details">
            <div><dt>학번</dt><dd>{student.studentId}</dd></div>
            <div><dt>소속 대학</dt><dd>{student.college}</dd></div>
            <div><dt>학과</dt><dd>{student.department}</dd></div>
            {student.year && <div><dt>학년</dt><dd>{student.year}학년</dd></div>}
          </dl>
        </div>
        {reservation ? (
          <div className="home-hero-actions">
            <Button onPress={onReserve} variant="primary">좌석 변경</Button>
            <Button onPress={onRequestReturn} variant="neutral">좌석 반납</Button>
          </div>
        ) : <Button className="reserve-button" onPress={onReserve} variant="primary">열람실 현황 및 좌석 예약</Button>}
      </section>

      {reservation ? (
        <ActiveReservationCard reservation={reservation} room={reservationRoom} now={now} onViewReservation={onViewReservation} />
      ) : (
        <section className="home-card" aria-labelledby="my-reservation-title">
          <h2 id="my-reservation-title">내 예약</h2>
          <p className="reservation-empty">현재 예약된 좌석이 없어요.</p>
        </section>
      )}

      <section className={`home-card${reservation ? '' : ' favorite-unreserved'}`} aria-labelledby="favorite-title">
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
            <span className="congestion-status">{!apiMode && room.congestion + ' · '}{room.usage}%</span>
          </div>
        ))}
      </section>
    </main>
  )
}
