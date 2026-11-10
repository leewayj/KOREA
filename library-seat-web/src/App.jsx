import { useEffect, useRef, useState } from 'react'
import HomePage from './components/HomePage'
import SeatPage from './components/SeatPage'
import ReservationPage from './components/ReservationPage'
import { createPreviewReservation, readPreviewReservation, savePreviewReservation, reservationDuration } from './data/reservation'
import { rooms } from './data/rooms'
import './App.css'

function getRoute() {
  const [page, roomId] = window.location.hash.slice(1).split('/')
  if (['seats', 'selected'].includes(page) && rooms.some((room) => room.id === roomId)) return { page, roomId }
  return { page: ['rooms', 'reservation'].includes(page) ? page : 'home', roomId: null }
}

function Icon({ name }) {
  return <img src={`/assets/${name}.svg`} alt="" draggable="false" />
}

function RoomStatusCard({ room, onSelect }) {
  return (
    <button className="room-card" onClick={() => onSelect(room)} aria-label={`${room.name} 예약하기`}>
      <span className="room-card-heading">
        <span className="room-name">{room.name}</span>
        <span className="room-action">예약하기 →</span>
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
  const [reservation, setReservation] = useState(readPreviewReservation)
  const [menuOpen, setMenuOpen] = useState(false)
  const [returnOpen, setReturnOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const menuButton = useRef(null)
  const menuPanel = useRef(null)
  const reservationRoom = rooms.find((item) => item.id === reservation?.roomId)
  const changeMode = page === 'selected' && reservation?.roomId === roomId
  const pageTitle = { home: 'HOME', rooms: '열람실 좌석 현황', seats: '좌석 선택', selected: '좌석 선택', reservation: '예약 정보 조회' }[page]

  useEffect(() => { savePreviewReservation(reservation) }, [reservation])

  useEffect(() => {
    if (page === 'selected' && reservation?.roomId !== roomId) {
      window.location.replace(`#seats/${roomId}`)
    }
  }, [page, roomId, reservation?.roomId])

  useEffect(() => {
    const onHashChange = () => {
      setRoute(getRoute())
      setSelectedSeat(null)
      setReturnOpen(false)
      setMenuOpen(false)
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

  useEffect(() => {
    if (!menuOpen) return
    const trigger = menuButton.current
    menuPanel.current?.querySelector('button')?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMenuOpen(false)
      if (event.key !== 'Tab') return
      const buttons = menuPanel.current?.querySelectorAll('button')
      if (!buttons?.length) return
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
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      trigger?.focus()
    }
  }, [menuOpen])

  function showNotice(message) {
    setMenuOpen(false)
    setNotice(message)
  }

  function navigate(nextPage) {
    setMenuOpen(false)
    setNotice('')
    setSelectedSeat(null)
    setReturnOpen(false)
    window.location.hash = nextPage
    setRoute(getRoute())
    window.scrollTo({ top: 0 })
  }

  return (
    <div className={`app-shell${['seats', 'selected'].includes(page) ? ' seat-shell' : page === 'reservation' ? ' reservation-shell' : ''}`}>
      <header className="app-header" inert={selectedSeat !== null || returnOpen}>
        <div className="navigation">
          <button className={`icon-button${page === 'home' ? ' account-icon' : ''}`} aria-label={page === 'home' ? '내 계정' : page === 'seats' ? '열람실 목록으로 돌아가기' : page === 'selected' ? '예약 정보로 돌아가기' : 'HOME'} onClick={() => page === 'home' ? showNotice('내 계정 화면은 준비 중입니다.') : navigate(page === 'seats' ? 'rooms' : page === 'selected' ? 'reservation' : 'home')}>
            <Icon name={page === 'home' ? 'account-v2' : ['seats', 'selected', 'reservation'].includes(page) ? 'seat-back-v2' : 'nav-home-v2'} />
          </button>
          <h1>{pageTitle}</h1>
          <button ref={menuButton} className="icon-button" aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'} aria-expanded={menuOpen} aria-controls={menuOpen ? 'shortcut-menu' : undefined} onClick={() => { setNotice(''); setMenuOpen(!menuOpen) }}>
            <Icon name="nav-menu-v2" />
          </button>
        </div>
      </header>

      {page === 'home' ? (
        <HomePage reservation={reservation} reservationRoom={reservationRoom} onViewReservation={() => navigate('reservation')} menuOpen={menuOpen} onReserve={() => navigate('rooms')} onManage={() => showNotice('선호 좌석 관리는 준비 중입니다.')} />
       ) : ['seats', 'selected'].includes(page) ? (
        <SeatPage key={`${page}/${roomId}`} changeMode={changeMode} onContinue={() => navigate('reservation')} room={room} menuOpen={menuOpen} selectedSeat={selectedSeat}
          onSelect={setSelectedSeat} mySeat={reservation?.roomId === roomId ? reservation.seat : undefined}
          onReserve={(seat) => {
            if (changeMode) {
              setReservation((current) => ({ ...current, seat }))
              navigate('reservation')
            } else {
              setReservation(createPreviewReservation(roomId, seat))
              navigate('reservation')
            }
          }}
          onRefresh={() => showNotice('현재 미리보기 좌석 현황입니다.')}
        />
      ) : page === 'reservation' ? (
        reservation ? <ReservationPage reservation={reservation} room={reservationRoom} menuOpen={menuOpen}
          returnOpen={returnOpen} onReturnOpenChange={setReturnOpen}
          onReturn={() => { setReservation(null); navigate('home') }}
          onChange={() => navigate(`selected/${reservation.roomId}`)}
          onExtend={() => {
            setReservation((current) => ({ ...current, endsAt: current.endsAt + reservationDuration }))
            showNotice('미리보기 예약을 2시간 연장했습니다.')
          }}
        /> : <main className="reservation-content" inert={menuOpen}><div className="reservation-summary"><h2>내 예약 정보</h2><p>현재 예약된 좌석이 없어요.</p></div><button className="room-card" onClick={() => navigate('rooms')}>좌석 예약하기 →</button></main>
      ) : (
        <main className="room-list" aria-label="열람실별 좌석 현황" inert={menuOpen}>
          {rooms.map((room) => <RoomStatusCard key={room.id} room={room} onSelect={(selected) => navigate(`seats/${selected.id}`)} />)}
        </main>
      )}

      {menuOpen && (
        <>
          <div className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <section ref={menuPanel} id="shortcut-menu" className="shortcut-menu" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
            <div className="shortcut-heading">
              <h2 id="shortcut-title">바로가기</h2>
              <button className="close-button" aria-label="바로가기 닫기" onClick={() => setMenuOpen(false)}><Icon name="menu-close-v2" /></button>
            </div>
            <nav className="shortcut-tiles" aria-label="바로가기">
              <button className={`shortcut-tile home-shortcut${page === 'home' ? ' active' : ''}`} aria-current={page === 'home' ? 'page' : undefined} onClick={() => navigate('home')}><Icon name={page === 'home' ? 'tile-home-active-v2' : 'tile-home-v2'} /><span>HOME</span></button>
              <button className={`shortcut-tile seats-shortcut${page !== 'home' ? ' active' : ''}`} aria-current={page !== 'home' ? 'page' : undefined} onClick={() => navigate('rooms')}><Icon name={page !== 'home' ? 'tile-seats-active-v2' : 'tile-seats-v2'} /><span>좌석 현황</span></button>
              <button className="shortcut-tile" onClick={() => showNotice('안내사항은 준비 중입니다.')}><Icon name="tile-info-v2" /><span>안내사항</span></button>
            </nav>
          </section>
        </>
      )}
      <div className={`notice${notice ? ' visible' : ''}`} role="status" aria-live="polite">{notice}</div>
    </div>
  )
}

export default App
