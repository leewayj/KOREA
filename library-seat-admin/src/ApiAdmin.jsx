import { useEffect, useRef, useState } from 'react'
import { list, request } from './api'
import { inputTime, parseTime, dateTime } from './data/store'

export default function ApiAdmin() {
  const [seats, setSeats] = useState([])
  const [reservations, setReservations] = useState([])
  const [version, setVersion] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const pending = useRef(false)
  const [editing, setEditing] = useState(null)
  const [room, setRoom] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    Promise.all([list('/seats', controller.signal), list('/reservations', controller.signal)])
      .then(([nextSeats, nextReservations]) => {
        if (controller.signal.aborted) return
        setSeats(nextSeats)
        setReservations(nextReservations)
        setError('')
      }).catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [version])
  useEffect(() => {
    const interval = setInterval(() => { if (!pending.current) setVersion(value => value + 1) }, 15000)
    return () => clearInterval(interval)
  }, [])
  async function mutate(path, method, body) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setMessage('')
    try {
      await request(path, { method, body })
      setEditing(null)
      setMessage('서버에 저장했습니다.')
    } catch (failure) { setMessage(failure.message) }
    finally {
      pending.current = false
      setBusy(false)
      setVersion(value => value + 1)
    }
  }
  function submit(event) {
    event.preventDefault()
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const starts_at = Math.floor(parseTime(fields.start) / 1000)
    const ends_at = Math.floor(parseTime(fields.end) / 1000)
    if (!Number.isFinite(starts_at) || !Number.isFinite(ends_at) || ends_at <= starts_at) {
      setMessage('종료일시를 시작일시 이후로 입력하세요.')
      return
    }
    if (editing?.id) mutate(`/admin/reservations/${editing.id}`, 'PATCH', { starts_at, ends_at, status: fields.status })
    else mutate('/admin/reservations', 'POST', { seat_id: Number(fields.seat_id), s_id: fields.s_id, starts_at, ends_at })
  }
  const rooms = [...new Map(seats.map(seat => [seat.room_code, seat.room_name])).entries()]
  const visibleSeats = seats.filter(seat => !room || seat.room_code === room)
  const visibleReservations = reservations.filter(reservation => visibleSeats.some(seat => seat.seat_id === reservation.seat_id))
  return <div className="app-shell"><main>
    <div className="row"><h1>도서관 좌석 관리</h1><button disabled={busy || loading} onClick={() => setVersion(value => value + 1)}>새로고침</button></div>
    {error && <p role="alert">{error}</p>}
    {loading && <p role="status">서버 정보를 확인하는 중입니다.</p>}
    <label>열람실 <select value={room} onChange={event => setRoom(event.target.value)}><option value="">전체</option>{rooms.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
    <section className="card"><h2>좌석 현황</h2><div className="seat-list">{visibleSeats.map(seat => <article className="seat-row" key={seat.seat_id}><strong>{seat.room_name} · {seat.seat_number}번</strong><p>{seat.reservation_state === 'RESERVED' ? '예약 중' : '예약 가능'}</p></article>)}</div></section>
    <button disabled={busy || !seats.length} onClick={() => { setEditing({}); setMessage('') }}>예약 등록</button>
    {editing && <section className="card"><form key={editing.id || 'new'} onSubmit={submit} className="api-auth" style={{ margin: 0 }}>
      <h2>{editing.id ? '예약 수정' : '예약 등록'}</h2>
      {!editing.id && <><label>등록된 사용자 학번<input name="s_id" required pattern="[0-9]{10}" /></label><label>좌석<select name="seat_id" required>{seats.map(seat => <option key={seat.seat_id} value={seat.seat_id}>{seat.room_name} · {seat.seat_number}번</option>)}</select></label></>}
      <label>시작일시 (한국 시간)<input type="datetime-local" name="start" required defaultValue={inputTime(editing.starts_at ? editing.starts_at * 1000 : Date.now())} /></label>
      <label>종료일시 (한국 시간)<input type="datetime-local" name="end" required defaultValue={inputTime(editing.ends_at ? editing.ends_at * 1000 : Date.now() + 7200000)} /></label>
      {editing.id && <label>상태<select name="status" defaultValue={editing.status}>{['CONFIRMED', 'ENDED', 'CANCELLED'].map(status => <option key={status}>{status}</option>)}</select></label>}
      <button disabled={busy} type="submit">저장</button><button disabled={busy} type="button" onClick={() => setEditing(null)}>취소</button>
    </form></section>}
    {message && <p role="status">{message}</p>}
    <section className="card"><h2>예약 목록</h2>{visibleReservations.length === 0 && !loading && <p>예약이 없습니다.</p>}{visibleReservations.map(reservation => {
      const seat = seats.find(item => item.seat_id === reservation.seat_id)
      return <article className="seat-row" key={reservation.id}><h3>예약 #{reservation.id} · {seat?.room_name} {seat?.seat_number}번</h3><p>{dateTime(reservation.starts_at * 1000)} – {dateTime(reservation.ends_at * 1000)}</p><p>{reservation.effective_status || reservation.status}</p>
        <button disabled={busy} onClick={() => { setEditing(reservation); setMessage('') }}>수정</button> <button disabled={busy} onClick={() => { if (window.confirm(`예약 #${reservation.id}을 삭제할까요?`)) mutate(`/admin/reservations/${reservation.id}`, 'DELETE') }}>삭제</button>
      </article>
    })}</section>
  </main></div>
}
