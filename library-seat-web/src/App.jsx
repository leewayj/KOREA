import { useEffect, useRef, useState } from 'react'
import HomePage from './components/HomePage'
import SeatPage from './components/SeatPage'
import ReservationPage from './components/ReservationPage'
import ReturnSeatDialog from './components/ReturnSeatDialog'
import ExpiredReservationPage from './components/ExpiredReservationPage'
import { createPreviewReservation, readPreviewReservation, savePreviewReservation, isReservationActive, canChangeSeat, changeReservationSeat, extendReservation, createReservationFixture, expirationWarningMs, isReservationEndingSoon, formatDuration } from './data/reservation'
import { rooms as previewRooms } from './data/rooms'
import { reservationApiEnabled, fetchSeats, fetchSeat, fetchMyReservation, reserveApiSeat, moveApiReservation, extendApiReservation, endApiReservation } from './data/reservationApi'
import { session } from './api'
import './App.css'

const fixtureName = import.meta.env.DEV ? new URLSearchParams(window.location.search).get('preview') : null
const fixture = createReservationFixture(fixtureName)

const apiMode = reservationApiEnabled && !(import.meta.env.DEV && new URLSearchParams(window.location.search).has('preview'))
const roomIdsByCode = { R1: 'reading-1', R2: 'reading-2', FOCUS: 'focus', HOLMZ: 'holmz' }

function toWebReservation(reservation, seat) {
  return {
    id: reservation.id,
    roomId: roomIdsByCode[seat.room_code],
    seat: Number(seat.seat_number),
    startsAt: reservation.starts_at * 1000,
    endsAt: reservation.ends_at * 1000,
    effectiveStatus: reservation.effective_status,
    studentId: session()?.user?.s_id,
  }
}

function getRoute() {
  const [page, roomId] = window.location.hash.slice(1).split('/')
  if (['seats', 'selected'].includes(page) && previewRooms.some((room) => room.id === roomId)) return { page, roomId }
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

function App({ accountControl }) {
  const [route, setRoute] = useState(getRoute)
  const { page, roomId } = route
  const [apiSeats, setApiSeats] = useState([])
  const [loading, setLoading] = useState(apiMode)
  const [loadError, setLoadError] = useState('')
  const [loadVersion, setLoadVersion] = useState(0)
  const reservationReads = useRef(null)
  const savingReservation = useRef(false)
  const [saving, setSaving] = useState(false)
  const rooms = apiMode ? previewRooms.map((room) => {
    const seats = apiSeats.filter((seat) => roomIdsByCode[seat.room_code] === room.id)
    const reserved = seats.filter((seat) => seat.reservation_state === 'RESERVED').length
    const total = seats.length
    return { ...room, total, reserved, available: total - reserved, usage: total ? Math.round(reserved / total * 100) : 0 }
  }) : previewRooms
  const room = rooms.find((item) => item.id === roomId)
  const [selectedSeat, setSelectedSeat] = useState(null)
  const [reservation, setReservation] = useState(() => fixture || (apiMode ? null : readPreviewReservation()))
  const [now, setNow] = useState(Date.now)
  const activeReservation = isReservationActive(reservation, now) ? reservation : null
  const [returnOpen, setReturnOpen] = useState(false)
  const returnTrigger = useRef(null)
  const showReturnDialog = returnOpen && Boolean(activeReservation) && ['home', 'reservation'].includes(page)
  const [notice, setNotice] = useState('')
  const appShell = useRef(null)
  const reservationRoom = rooms.find((item) => item.id === reservation?.roomId)
  const changeMode = ['seats', 'selected'].includes(page) && Boolean(activeReservation)
  const endingSoon = page === 'reservation' && isReservationEndingSoon(reservation, now)
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

  useEffect(() => { if (!fixture && !apiMode) savePreviewReservation(reservation) }, [reservation])

  useEffect(() => {
    if (!apiMode) return
    const controller = new AbortController()

    reservationReads.current = controller
    const poll = { inFlight: false, hasSnapshot: false }

    async function sync() {
      if (poll.inFlight || controller.signal.aborted || savingReservation.current) return
      poll.inFlight = true
      try {
        const [seats, saved] = await Promise.all([
          fetchSeats(controller.signal),
          session() ? fetchMyReservation(controller.signal) : null,
        ])
        const seat = saved && (seats.find((item) => item.seat_id === saved.seat_id)
          ?? await fetchSeat(saved.seat_id, controller.signal))
        if (controller.signal.aborted) return
        if (saved && !roomIdsByCode[seat?.room_code]) throw new Error('Unknown reservation room')
        poll.hasSnapshot = true
        setApiSeats(seats)
        setReservation(saved ? toWebReservation(saved, seat) : null)
        setLoadError('')
      } catch (error) {
        if (!controller.signal.aborted && !poll.hasSnapshot) {
          setLoadError(error.message || '예약 서버에 연결할 수 없어요.')
        }
      } finally {
        poll.inFlight = false
        if (!controller.signal.aborted) setLoading(false)
      }
    }

    sync()
    const timer = window.setInterval(sync, 5000)
    window.addEventListener('focus', sync)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      window.removeEventListener('focus', sync)
    }
  }, [loadVersion])

  function refresh() {
    setLoading(true)
    setLoadError('')
    setLoadVersion((version) => version + 1)
  }

  function clearReservation() {
    setReservation(null)
  }

  async function updateApiReservation(send, onSuccess) {
    if (savingReservation.current || loading) return
    savingReservation.current = true
    reservationReads.current?.abort()
    setSaving(true)
    try {
      onSuccess(await send())
    } catch (error) {
      setSelectedSeat(null)
      setReturnOpen(false)
      showNotice(error.status ? error.message : '요청 결과를 확인할 수 없어요. 예약 정보를 다시 확인해 주세요.')
    } finally {
      refresh()
      savingReservation.current = false
      setSaving(false)
    }
  }

  function bookSeat(number) {
    if (!session()) { window.dispatchEvent(new Event('korea-login')); return }
    const seat = apiSeats.find((item) => roomIdsByCode[item.room_code] === roomId
      && Number(item.seat_number) === number && item.reservation_state === 'AVAILABLE')
    if (!seat) {
      setSelectedSeat(null)
      showNotice('선택한 좌석은 더 이상 예약할 수 없어요.')
      return
    }
    const send = activeReservation
      ? () => moveApiReservation(activeReservation.id, seat.seat_id)
      : () => reserveApiSeat(seat.seat_id)
    return updateApiReservation(send, (saved) => {
      setReservation(toWebReservation(saved, seat))
      navigate('reservation')
    })
  }

  function returnSeat() {
    const finish = () => { clearReservation(); navigate('home') }
    if (apiMode) return updateApiReservation(() => endApiReservation(reservation.id), finish)
    finish()
  }

  useEffect(() => {
    const updateClock = () => setNow(Date.now())
    updateClock()
    const timer = window.setInterval(updateClock, 1000)
    const untilWarning = reservation ? reservation.endsAt - expirationWarningMs - Date.now() : 0
    const warningTimer = untilWarning > 0 && untilWarning <= 2_147_483_647
      ? window.setTimeout(updateClock, untilWarning)
      : null
    window.addEventListener('focus', updateClock)
    return () => {
      window.clearInterval(timer)
      if (warningTimer !== null) window.clearTimeout(warningTimer)
      window.removeEventListener('focus', updateClock)
    }
  }, [reservation])

  useEffect(() => {
    if (loading || loadError) return
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
  }, [page, roomId, reservation, activeReservation, loading, loadError])

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
    if (savingReservation.current || !isReservationActive(reservation)) return
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
            <button className="icon-button" aria-label={['seats', 'selected'].includes(page) ? '열람실 목록으로 돌아가기' : endingSoon ? '홈으로 돌아가기' : 'HOME'} onClick={() => {
              if (['seats', 'selected'].includes(page)) navigate('rooms')
              else { if (page === 'expired') clearReservation(); navigate('home') }
            }}>
              <Icon name={['reservation', 'expired'].includes(page) && !endingSoon ? 'v02-home' : 'v02-back'} />
            </button>
          )}
          <h1>{pageTitle}</h1>
          {page === 'home' ? (accountControl ?? <span className="navigation-spacer" aria-hidden="true" />) : <span className="navigation-spacer" aria-hidden="true" />}
        </div>
      </header>

      {loading || loadError ? (
        <main className="room-list" aria-busy={loading}>
          <p role="status">{loadError || '좌석과 예약 정보를 불러오는 중이에요.'}</p>
          {loadError && <button className="room-card" onClick={refresh}>다시 시도</button>}
        </main>
      ) : page === 'home' ? (
        <HomePage rooms={rooms} apiMode={apiMode} returnOpen={showReturnDialog} onRequestReturn={requestReturn} now={now} reservation={activeReservation} reservationRoom={reservationRoom} onViewReservation={() => navigate('reservation')} onReserve={() => navigate('rooms')} onManage={() => showNotice('선호 좌석 관리는 준비 중입니다.')} />
       ) : ['seats', 'selected'].includes(page) ? (
        <SeatPage key={`${page}/${roomId}`} changeMode={changeMode} onContinue={() => navigate('reservation')} room={room} selectedSeat={selectedSeat} booking={saving} apiMode={apiMode}
          serverSeats={apiMode ? apiSeats.filter((seat) => roomIdsByCode[seat.room_code] === roomId) : null}
          onSelect={setSelectedSeat} previousSeat={activeReservation?.seat} previousRoom={reservationRoom} mySeat={activeReservation?.roomId === roomId ? activeReservation.seat : undefined}
          onReserve={(seat) => {
            if (apiMode) { bookSeat(seat); return }
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
          onRefresh={apiMode ? refresh : () => showNotice('현재 미리보기 좌석 현황입니다.')}
        />
      ) : page === 'expired' && reservation ? (
        <ExpiredReservationPage reservation={reservation} room={reservationRoom} now={now}
          onReserve={() => { clearReservation(); navigate('rooms') }}
          onConfirm={() => { clearReservation(); navigate('home') }} />
      ) : page === 'reservation' ? (
        activeReservation ? <ReservationPage saving={saving} now={now} endingSoon={endingSoon} reservation={reservation} room={reservationRoom}
          returnOpen={showReturnDialog} onRequestReturn={requestReturn}
          onChange={() => navigate(`selected/${reservation.roomId}`)}
          onExtend={() => {
            if (!isReservationActive(reservation)) { navigate('expired'); return }
            if (apiMode) {
              return updateApiReservation(
                () => extendApiReservation(reservation.id),
                (saved) => {
                  setReservation({ ...reservation, endsAt: saved.ends_at * 1000, effectiveStatus: saved.effective_status })
                  showNotice(`예약 시간이 ${formatDuration(saved.policy_default_duration_seconds * 1000)} 연장되었습니다.`)
                },
              )
            }
            setReservation((current) => extendReservation(current))
            showNotice('예약 시간이 2시간 연장되었습니다.')
          }}
        /> : <main className="reservation-content"><div className="reservation-summary"><h2>내 예약 정보</h2><p>현재 예약된 좌석이 없어요.</p></div><button className="room-card" onClick={() => navigate('rooms')}>좌석 예약하기 →</button></main>
      ) : (
        <main className="room-list" aria-label="열람실별 좌석 현황">
          {rooms.map((room) => <RoomStatusCard key={room.id} room={room} changeMode={Boolean(activeReservation)} onSelect={(selected) => navigate(`${isReservationActive(reservation) ? 'selected' : 'seats'}/${selected.id}`)} />)}
        </main>
      )}

      {showReturnDialog && <ReturnSeatDialog triggerRef={returnTrigger} onOpenChange={setReturnOpen} saving={saving}
        onConfirm={returnSeat} />}

      <div className={`notice${notice ? ' visible' : ''}`} role="status" aria-live="polite">{notice}</div>
    </div>
  )
}

export default App
