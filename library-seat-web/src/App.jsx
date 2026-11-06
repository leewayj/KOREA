import { useEffect, useRef, useState } from 'react'
import './App.css'

// Frontend preview data. Replace this boundary when the room API is connected.
const rooms = [
  { id: 'reading-1', name: '제1열람실 (2F)', total: 72, available: 47, reserved: 25 },
  { id: 'reading-2', name: '제2열람실 (4F)', total: 72, available: 47, reserved: 25 },
  { id: 'focus', name: '집중열람실 (4F)', total: 72, available: 47, reserved: 25 },
  { id: 'holmz', name: '노상일 HOLMZ (4F)', total: 72, available: 47, reserved: 25 },
]

function Icon({ name }) {
  return <img src={`/assets/${name}.svg`} alt="" draggable="false" />
}

function RoomStatusCard({ room, menuOpen, onSelect }) {
  return (
    <button className="room-card" onClick={() => onSelect(room)} aria-label={`${room.name} 예약하기`}>
      <span className="room-card-heading">
        <span className="room-name">{room.name}</span>
        <span className="room-action">{menuOpen ? '보기 →' : '예약하기 →'}</span>
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
  const [menuOpen, setMenuOpen] = useState(false)
  const [notice, setNotice] = useState('')
  const menuButton = useRef(null)
  const menuPanel = useRef(null)

  useEffect(() => {
    if (!notice) return
    const timeout = window.setTimeout(() => setNotice(''), 3500)
    return () => window.clearTimeout(timeout)
  }, [notice])

  useEffect(() => {
    if (!menuOpen) return
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
      menuButton.current?.focus()
    }
  }, [menuOpen])

  function showNotice(message) {
    setMenuOpen(false)
    setNotice(message)
  }

  return (
    <div className="app-shell">
      <header className={`app-header${menuOpen ? ' menu-open' : ''}`}>
        <div className="navigation">
          <button className="icon-button" aria-label="HOME" onClick={() => showNotice('HOME 화면은 준비 중입니다.')}>
            <Icon name={menuOpen ? 'home-menu-open' : 'home'} />
          </button>
          <h1>열람실 좌석 현황</h1>
          <button ref={menuButton} className="icon-button" aria-label={menuOpen ? '메뉴 닫기' : '메뉴 열기'} aria-expanded={menuOpen} aria-controls={menuOpen ? 'shortcut-menu' : undefined} onClick={() => { setNotice(''); setMenuOpen(!menuOpen) }}>
            <Icon name={menuOpen ? 'menu-open' : 'menu'} />
          </button>
        </div>
      </header>

      <main className="room-list" aria-label="열람실별 좌석 현황" inert={menuOpen}>
        {rooms.map((room) => <RoomStatusCard key={room.id} room={room} menuOpen={menuOpen} onSelect={(selected) => showNotice(`${selected.name} 좌석 예약은 준비 중입니다.`)} />)}
      </main>

      {menuOpen && (
        <>
          <div className="menu-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <section ref={menuPanel} id="shortcut-menu" className="shortcut-menu" role="dialog" aria-modal="true" aria-labelledby="shortcut-title">
            <div className="shortcut-heading">
              <h2 id="shortcut-title">바로가기</h2>
              <button className="close-button" aria-label="바로가기 닫기" onClick={() => setMenuOpen(false)}><Icon name="close" /></button>
            </div>
            <nav className="shortcut-tiles" aria-label="바로가기">
              <button className="shortcut-tile" onClick={() => showNotice('HOME 화면은 준비 중입니다.')}><Icon name="home-tile" /><span>HOME</span></button>
              <button className="shortcut-tile active" aria-current="page" onClick={() => setMenuOpen(false)}><Icon name="seats" /><span>좌석 현황</span></button>
              <button className="shortcut-tile" onClick={() => showNotice('안내사항은 준비 중입니다.')}><Icon name="info" /><span>안내사항</span></button>
            </nav>
          </section>
        </>
      )}
      <div className={`notice${notice ? ' visible' : ''}`} role="status" aria-live="polite">{notice}</div>
    </div>
  )
}

export default App
