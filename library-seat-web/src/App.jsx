import { useEffect, useRef, useState } from 'react'
import HomePage from './components/HomePage'
import SeatPage from './components/SeatPage'
import ReservationPage from './components/ReservationPage'
import ReturnSeatDialog from './components/ReturnSeatDialog'
import ExpiredReservationPage from './components/ExpiredReservationPage'
import { createPreviewReservation, readPreviewReservation, savePreviewReservation, isReservationActive, canChangeSeat, changeReservationSeat, extendReservation, createReservationFixture } from './data/reservation'
import { rooms } from './data/rooms'
import './App.css'

const fixtureName = import.meta.env.DEV ? new URLSearchParams(window.location.search).get('preview') : null
const fixture = createReservationFixture(fixtureName)

function getRoute() {
  const [page, roomId] = window.location.hash.slice(1).split('/')
  if (['seats', 'selected'].includes(page) && rooms.some((room) => room.id === roomId)) return { page, roomId }
  return { page: ['rooms', 'reservation', 'expired'].includes(page) ? page : 'home', roomId: null }
}

function Icon({ name }) {
  return <img src={`/assets/${name}.svg`} alt="" draggable="false" />
}

function RoomStatusCard({ room, onSelect, changeMode }) {
  const action = changeMode ? '좌석 변경' : '예약하기'
  return (
    <button className="room-card" onClick={() => onSelect(room)} aria-label={`${room.name} ${action}`}>
      <span className="room-card-heading">
        <span className="room-name">{room.name}</span>
        <span className="room-action">{action} →</span>
      </span>
      <span className="room-stats">
        <span className="room-stat"><span className="stat-label">전체</span><strong>{room.total}석</strong></span>
        <span className="room-stat available"><span className="stat-label">예약 가능</span><strong>{room.available}석</strong></span>
        <span className="room-stat"><span className="stat-label">예약 중</span><strong>{room.reserved}석</strong></span>
      </span>
    </button>
  )
}

function App() {
  const [route, setRoute] = useState(getRoute)
  const { page, roomId } = route
  const room = rooms.find((item) => item.id === roomId)
  const [selectedSeat, setSelectedSeat] = useState(null)
  const [reservation, setReservation] = useState(() => fixture || readPreviewReservation())
  const [now, setNow] = useState(Date.now)
  const activeReservation = isReservationActive(reservation, now) ? reservation : null
  const [returnOpen, setReturnOpen] = useState(false)
  const returnTrigger = useRef(null)
  const showReturnDialog = returnOpen && Boolean(activeReservation) && ['home', 'reservation'].includes(page)
  const [notice, setNotice] = useState('')
  const appShell = useRef(null)
  const reservationRoom = rooms.find((item) => item.id === reservation?.roomId)
  const changeMode = ['seats', 'selected'].includes(page) && Boolean(activeReservation)
  const pageTitle = { home: 'HOME', rooms: '열람실 좌석 현황', seats: '좌석 선택', selected: '좌석 선택', reservation: '예약 정보 조회', expired: '예약 종료' }[page]

  function navigate(nextPage) {
    setNotice('')
    setSelectedSeat(null)
    setReturnOpen(false)
    window.location.hash = nextPage
    setRoute(getRoute())
  }

  useEffect(() => {
    appShell.current?.querySelector('main')?.scrollTo({ top: 0 })
  }, [page, roomId])

  useEffect(() => { if (!fixture) savePreviewReservation(reservation) }, [reservation])

  useEffect(() => {
    if (!reservation) return
    const updateClock = () => setNow(Date.now())
    updateClock()
    const timer = window.setInterval(updateClock, 1000)
    window.addEventListener('focus', updateClock)
    return () => { window.clearInterval(timer); window.removeEventListener('focus', updateClock) }
  }, [reservation])

  useEffect(() => {
    const reservationPages = ['reservation', 'selected']
    if (reservation && !activeReservation && reservationPages.includes(page)) {
      window.location.replace('#expired')
    } else if (page === 'expired' && activeReservation) {
      window.location.replace('#reservation')
    } else if (page === 'expired' && !reservation) {
      window.location.replace('#home')
    } else if (page === 'selected' && !activeReservation) {
      window.location.replace(`#seats/${roomId}`)
    } else if (page === 'seats' && activeReservation) {
      window.location.replace(`#selected/${roomId}`)
    }
  }, [page, roomId, reservation, activeReservation])

  useEffect(() => {
    const onHashChange = () => {
      setRoute(getRoute())
      setSelectedSeat(null)
      setReturnOpen(false)
      setNotice('')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    document.title = `${pageTitle} · 열람실 좌석 예약`
  }, [pageTitle])

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(''), 3500)
    return () => window.clearTimeout(timeout)
  }, [notice])

  function requestReturn(event) {
    if (!isReservationActive(reservation)) return
    returnTrigger.current = event.target
    setReturnOpen(true)
  }

  function showNotice(message) {
    setNotice(message)
  }

  return (
    <div ref={appShell} className={`app-shell${['seats', 'selected'].includes(page) ? ' seat-shell' : ['reservation', 'expired'].includes(page) ? ' reservation-shell' : ''}`}>
      <header className="app-header" inert={selectedSeat !== null || showReturnDialog}>
        <div className="navigation">
          {page === 'home' ? <span className="navigation-spacer" aria-hidden="true" /> : (
            <button className="icon-button" aria-label={['seats', 'selected'].includes(page) ? '열람실 목록으로 돌아가기' : 'HOME'} onClick={() => {
              if (['seats', 'selected'].includes(page)) navigate('rooms')
              else { if (page === 'expired') setReservation(null); navigate('home') }
            }}>
              <Icon name={page === 'rooms' ? 'nav-home-v2' : 'seat-back-v2'} />
            </button>
          )}
          <h1>{pageTitle}</h1>
          <span className="navigation-spacer" aria-hidden="true" />
        </div>
      </header>

      {page === 'home' ? (
        <HomePage returnOpen={showReturnDialog} onRequestReturn={requestReturn} now={now} reservation={activeReservation} reservationRoom={reservationRoom} onViewReservation={() => navigate('reservation')} onReserve={() => navigate('rooms')} onManage={() => showNotice('선호 좌석 관리는 준비 중입니다.')} />
       ) : ['seats', 'selected'].includes(page) ? (
        <SeatPage key={`${page}/${roomId}`} changeMode={changeMode} onContinue={() => navigate('reservation')} room={room} selectedSeat={selectedSeat}
          onSelect={setSelectedSeat} previousSeat={activeReservation?.seat} previousRoom={reservationRoom} mySeat={activeReservation?.roomId === roomId ? activeReservation.seat : undefined}
          onReserve={(seat) => {
            if (page === 'selected' || activeReservation) {
              if (!isReservationActive(reservation)) { navigate('expired'); return }
              if (!canChangeSeat(reservation, roomId, seat)) return
              setReservation((current) => changeReservationSeat(current, roomId, seat))
              navigate('reservation')
            } else {
              setReservation(createPreviewReservation(roomId, seat))
              navigate('reservation')
            }
          }}
          onRefresh={() => showNotice('현재 미리보기 좌석 현황입니다.')}
        />
      ) : page === 'expired' && reservation ? (
        <ExpiredReservationPage reservation={reservation} room={reservationRoom} now={now}
          onReserve={() => { setReservation(null); navigate('rooms') }}
          onConfirm={() => { setReservation(null); navigate('home') }} />
      ) : page === 'reservation' ? (
        activeReservation ? <ReservationPage now={now} reservation={reservation} room={reservationRoom}
          returnOpen={showReturnDialog} onRequestReturn={requestReturn}
          onChange={() => navigate(`selected/${reservation.roomId}`)}
          onExtend={() => {
            if (!isReservationActive(reservation)) { navigate('expired'); return }
            setReservation((current) => extendReservation(current))
            showNotice('예약 시간이 2시간 연장되었습니다.')
          }}
        /> : <main className="reservation-content"><div className="reservation-summary"><h2>내 예약 정보</h2><p>현재 예약된 좌석이 없어요.</p></div><button className="room-card" onClick={() => navigate('rooms')}>좌석 예약하기 →</button></main>
      ) : (
        <main className="room-list" aria-label="열람실별 좌석 현황">
          {rooms.map((room) => <RoomStatusCard key={room.id} room={room} changeMode={Boolean(activeReservation)} onSelect={(selected) => navigate(`${isReservationActive(reservation) ? 'selected' : 'seats'}/${selected.id}`)} />)}
        </main>
      )}

      {showReturnDialog && <ReturnSeatDialog triggerRef={returnTrigger} onOpenChange={setReturnOpen}
        onConfirm={() => { setReservation(null); navigate('home') }} />}

      <div className={`notice${notice ? ' visible' : ''}`} role="status" aria-live="polite">{notice}</div>
    </div>
  )
}

export default App
