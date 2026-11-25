import { test, beforeEach, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { login, request, session, logout } from '../api.js'
import { reserveApiSeat, fetchMyReservation, extendApiReservation } from './reservationApi.js'

let values
const originalStorage = globalThis.sessionStorage
const originalWindow = globalThis.window
beforeEach(() => {
  values = new Map()
  globalThis.sessionStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  }
  globalThis.window = { dispatchEvent() {} }
})
afterEach(() => {
  globalThis.sessionStorage = originalStorage
  globalThis.window = originalWindow
})

test('login token accompanies reservation requests and logout clears it', async (context) => {
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url === '/auth/login') return Response.json({ access_token: 'test-session', user: { s_id: '2099000001' } })
    assert.equal(options.headers.Authorization, 'Bearer test-session')
    if (url === '/reservations') {
      assert.deepEqual(JSON.parse(options.body), { seat_id: 2, def_time: 600 })
      return Response.json({ id: 4, seat_id: 2 }, { status: 201 })
    }
    return Response.json({ message: 'logged out' })
  })
  await login({ s_id: '2099000001' })
  assert.equal((await reserveApiSeat(2, 600)).id, 4)
  await logout()
  assert.equal(session(), null)
})

test('expired session is cleared and server error is retained', async (context) => {
  values.set('korea-user-session', JSON.stringify({ access_token: 'expired' }))
  context.mock.method(globalThis, 'fetch', async () => Response.json({ error: { message: '로그인이 만료되었습니다.' } }, { status: 401 }))
  await assert.rejects(request('/auth/me'), { status: 401, message: '로그인이 만료되었습니다.' })
  assert.equal(session(), null)
})

test('restoring a reservation queries the current user endpoint', async (context) => {
  values.set('korea-user-session', JSON.stringify({ access_token: 'current-user' }))
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/me/reservations?limit=500&offset=0')
    assert.equal(options.headers.Authorization, 'Bearer current-user')
    return Response.json([{ id: 8, effective_status: 'IN_USE' }])
  })
  assert.equal((await fetchMyReservation()).id, 8)
})

test('reservation extension sends the login token without a request body', async (context) => {
  values.set('korea-user-session', JSON.stringify({ access_token: 'current-user' }))
  context.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/reservations/8/extend')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers.Authorization, 'Bearer current-user')
    assert.equal(options.body, undefined)
    return Response.json({ id: 8, extension_count: 1 })
  })
  assert.equal((await extendApiReservation(8)).extension_count, 1)
})
