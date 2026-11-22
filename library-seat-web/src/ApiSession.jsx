import { Fragment, useEffect, useRef, useState } from 'react'
import { apiEnabled, session, login, logout, request } from './api'
import './api-session.css'

export default function ApiSession({ children }) {
  const admin = import.meta.env.VITE_API_ROLE === 'admin'
  const preview = import.meta.env.DEV && new URLSearchParams(location.search).has('preview')
  const [account, setAccount] = useState(session)
  const [accountMenu, setAccountMenu] = useState(false)
  const [register, setRegister] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useRef(null)
  useEffect(() => {
    const update = () => {
      setAccount(session())
      if (session()) dialog.current?.close()
      else if (admin && !dialog.current?.open) dialog.current?.showModal()
    }
    const open = () => {
      setAccountMenu(false)
      setRegister(false)
      setError('')
      if (!dialog.current?.open) dialog.current?.showModal()
    }
    window.addEventListener('korea-session', update)
    window.addEventListener('korea-login', open)
    if (apiEnabled && !preview && admin && !session()) open()
    return () => {
      window.removeEventListener('korea-session', update)
      window.removeEventListener('korea-login', open)
    }
  }, [admin, preview])
  if (!apiEnabled || preview) return children(null)
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
  const accountControl = (
    <button type="button" className="icon-button account-control" aria-label={account ? '내 계정' : '로그인'} aria-haspopup="dialog" disabled={busy} onClick={() => {
      setAccountMenu(Boolean(account))
      setRegister(false)
      setError('')
      dialog.current?.showModal()
    }}>
      <img src="/assets/account-v2.svg" alt="" />
    </button>
  )
  return <>
    <Fragment key={account?.user?.s_id || account?.admin?.username || 'guest'}>{children(accountControl)}</Fragment>
    <dialog ref={dialog} className="api-auth" aria-labelledby="api-login-title" onCancel={event => { if (busy) event.preventDefault() }}>
      <h2 id="api-login-title">{accountMenu ? '내 계정' : admin ? '관리자 로그인' : register ? '사용자 등록' : '학번 로그인'}</h2>
      {accountMenu ? (
        <div className="api-account-actions">
          <p>{account?.user?.s_id || account?.admin?.username}</p>
          {error && <p role="alert">{error}</p>}
          <button type="button" disabled={busy} onClick={async () => {
            setBusy(true)
            setError('')
            try {
              await logout()
              dialog.current?.close()
            } catch (failure) {
              setError(failure.message)
            } finally {
              setBusy(false)
            }
          }}>로그아웃</button>
          <button type="button" disabled={busy} onClick={() => dialog.current?.close()}>닫기</button>
        </div>
      ) : (
      <form onSubmit={submit}>
        <label>{admin ? '관리자 ID' : '학번 (숫자 10자리)'}<input name={admin ? 'username' : 's_id'} required pattern={admin ? undefined : '[0-9]{10}'} autoComplete="username" /></label>
        {admin && <label>비밀번호<input name="password" type="password" required autoComplete="current-password" /></label>}
        {register && ['name', 'college', 'department'].map((name, index) => <label key={name}>{['이름', '단과대학', '학과'][index]}<input name={name} required maxLength={100} /></label>)}
        {error && <p role="alert">{error}</p>}
        <button disabled={busy}>{busy ? '처리 중…' : register ? '등록하고 로그인' : '로그인'}</button>
        {!admin && <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError('') }}>{register ? '로그인으로 돌아가기' : '처음이라면 사용자 등록'}</button>}
        <button type="button" disabled={busy} onClick={() => dialog.current.close()}>닫기</button>
      </form>
      )}
    </dialog>
  </>
}
