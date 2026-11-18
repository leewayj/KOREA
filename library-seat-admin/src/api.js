export const apiEnabled = Boolean(import.meta.env.VITE_RESERVATION_API_URL)
const base = import.meta.env.VITE_RESERVATION_API_URL?.replace(/\/+$/, '') || ''
const role = import.meta.env.VITE_API_ROLE === 'admin' ? 'admin' : 'user'
const key = `korea-${role}-session`
export const session = () => {
  try { return JSON.parse(sessionStorage.getItem(key)) } catch { return null }
}
export function clearSession() {
  sessionStorage.removeItem(key)
  window.dispatchEvent(new Event('korea-session'))
}
export async function request(path, { body, ...options } = {}) {
  const token = session()?.access_token
  const response = await fetch(base + path, {
    ...options,
    headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const data = await response.json()
  if (!response.ok) {
    const error = new Error(data.error?.message || data.detail || '요청에 실패했습니다.')
    error.status = response.status
    if (response.status === 401 && token && !path.endsWith('/login')) clearSession()
    throw error
  }
  return data
}
export async function login(body) {
  const result = await request(role === 'admin' ? '/admin/auth/login' : '/auth/login', { method: 'POST', body })
  sessionStorage.setItem(key, JSON.stringify(result))
  window.dispatchEvent(new Event('korea-session'))
}
export async function logout() {
  try { await request(role === 'admin' ? '/admin/auth/logout' : '/auth/logout', { method: 'POST' }) }
  finally { clearSession() }
}
export async function list(path, signal) {
  const result = []
  for (let offset = 0; ; offset += 500) {
    const batch = await request(`${path}?limit=500&offset=${offset}`, { signal })
    result.push(...batch)
    if (batch.length < 500) return result
  }
}
