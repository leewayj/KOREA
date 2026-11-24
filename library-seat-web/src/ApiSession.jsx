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
  const [logoutConfirm, setLogoutConfirm] = useState(false)
  const dialog = useRef(null)
  const logoutDialog = useRef(null)
  const userLoginPage = apiEnabled && !preview && !admin && !account
  useEffect(() => {
    const update = () => {
      const currentAccount = session()
      setAccount(currentAccount)
      if (currentAccount) dialog.current?.close()
      else {
        setLogoutConfirm(false)
        if (admin && !dialog.current?.open) dialog.current?.showModal()
      }
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
  useEffect(() => {
    const currentDialog = logoutDialog.current
    if (logoutConfirm && !currentDialog?.open) currentDialog?.showModal()
    else if (!logoutConfirm && currentDialog?.open) currentDialog.close()
  }, [logoutConfirm])
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
    <button type="button" className="icon-button logout-control" aria-label="로그아웃" aria-haspopup="dialog" disabled={busy} onClick={() => {
      setError('')
      setLogoutConfirm(true)
    }}>
      <img src="/assets/logout-v2.svg" alt="" />
    </button>
  )
  return <>
    {userLoginPage ? (
      <LoginScreen
        register={register}
        busy={busy}
        error={error}
        onSubmit={submit}
        onToggleRegister={() => { setRegister(!register); setError('') }}
      />
    ) : <Fragment key={account?.user?.s_id || account?.admin?.username || 'guest'}>{children(accountControl)}</Fragment>}
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
    <dialog
      ref={logoutDialog}
      className="logout-confirmation"
      aria-labelledby="logout-confirmation-title"
      onCancel={event => { if (busy) event.preventDefault(); else setLogoutConfirm(false) }}
      onClick={event => { if (event.target === event.currentTarget && !busy) setLogoutConfirm(false) }}
    >
      <h2 id="logout-confirmation-title">로그아웃 하시겠습니까?</h2>
      <button type="button" className="logout-confirm-button" disabled={busy} onClick={async () => {
        if (busy) return
        setBusy(true)
        setError('')
        try {
          await logout()
          setLogoutConfirm(false)
        } catch (failure) {
          setError(failure.message)
        } finally {
          setBusy(false)
        }
      }}>{busy ? '처리 중…' : '확인'}</button>
    </dialog>
  </>
}

function LoginScreen({ register, busy, error, onSubmit, onToggleRegister }) {
  return (
    <section className="login-shell" aria-label={register ? '사용자 등록' : '로그인'}>
      <header className="login-header"><h1>{register ? '회원가입' : '로그인'}</h1></header>
      <main className="login-content">
        <form className={`login-form${register ? ' is-registering' : ''}`} onSubmit={onSubmit}>
          <div className="login-card">
            {register ? (
              <>
                <label className="login-field"><span>이름</span><input name="name" required maxLength={100} autoComplete="name" /></label>
                <label className="login-field"><span>학번 (숫자 10자리)</span><input name="s_id" required pattern="[0-9]{10}" inputMode="numeric" autoComplete="username" /></label>
                <label className="login-field"><span>단과대학</span><input name="college" required maxLength={100} /></label>
                <label className="login-field"><span>학과</span><input name="department" required maxLength={100} /></label>
              </>
            ) : (
              <label className="login-field"><span>학번 (숫자 10자리)</span><input name="s_id" required pattern="[0-9]{10}" inputMode="numeric" autoComplete="username" /></label>
            )}
            {error && <p className="login-error" role="alert">{error}</p>}
            {!register && <button className="login-register-link" type="button" disabled={busy} onClick={onToggleRegister}>회원가입→</button>}
            {register && <button className="login-register-link register-back" type="button" disabled={busy} onClick={onToggleRegister}>로그인으로 돌아가기</button>}
          </div>
          <button className="login-submit" type="submit" disabled={busy}>{busy ? '처리 중…' : register ? '회원가입 하기' : '로그인 하기'}</button>
        </form>
      </main>
    </section>
  )
}
