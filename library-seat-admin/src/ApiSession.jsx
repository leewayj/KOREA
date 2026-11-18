import { useEffect, useState } from 'react'
import { apiEnabled, session, login, logout, request } from './api'
import './api-session.css'

export default function ApiSession({ children }) {
  const admin = import.meta.env.VITE_API_ROLE === 'admin'
  const [account, setAccount] = useState(session)
  const [register, setRegister] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    const update = () => setAccount(session())
    window.addEventListener('korea-session', update)
    return () => window.removeEventListener('korea-session', update)
  }, [])
  if (!apiEnabled || (import.meta.env.DEV && new URLSearchParams(location.search).has('preview'))) return children
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    try {
      if (register) await request('/auth/register', { method: 'POST', body: fields })
      await login(admin ? fields : { s_id: fields.s_id })
    } catch (failure) { setError(failure.message) }
    finally { setBusy(false) }
  }
  if (!account) return <main className="api-auth"><h1>{admin ? '관리자 로그인' : register ? '사용자 등록' : '학번 로그인'}</h1>
    <form onSubmit={submit}>
      <label>{admin ? '관리자 ID' : '학번 (숫자 10자리)'}<input name={admin ? 'username' : 's_id'} required pattern={admin ? undefined : '[0-9]{10}'} autoComplete="username" /></label>
      {admin && <label>비밀번호<input name="password" type="password" required autoComplete="current-password" /></label>}
      {register && ['name', 'college', 'department'].map((name, index) => <label key={name}>{['이름', '단과대학', '학과'][index]}<input name={name} required maxLength={100} /></label>)}
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{busy ? '처리 중…' : register ? '등록하고 로그인' : '로그인'}</button>
      {!admin && <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError('') }}>{register ? '로그인으로 돌아가기' : '처음이라면 사용자 등록'}</button>}
    </form></main>
  return <><div className="api-account"><span>{account.user?.name || account.user?.s_id || account.admin?.username}</span><button disabled={busy} onClick={async () => {
    setBusy(true)
    try { await logout() } catch (failure) { setError(failure.message) } finally { setBusy(false) }
  }}>로그아웃</button></div>{children}</>
}
