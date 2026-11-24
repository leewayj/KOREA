import assert from 'node:assert/strict';
import test from 'node:test';
import { loadAdminData } from './adminApi.js';

const rooms = [{ id: 1, floor_id: 2, code: 'R1', name: '제1열람실' }];
function respond(t, responses) {
  t.mock.method(globalThis, 'fetch', async (url) => {
    const path = url.replace(/^\/api/, '').split('?')[0];
    return Object.hasOwn(responses, path)
      ? Response.json(responses[path])
      : new Response('The page could not be found', { status: 404 });
  });
}

test('모든 API가 실패하면 빈 통계와 실제 0건을 구분한다', async (t) => {
  respond(t, {});
  const data = await loadAdminData();
  assert.equal(data.roomsKnown, false);
  assert.deepEqual(data.rooms.map((room) => room.id), ["1", "2", "3", "4"]);
  assert.ok(data.rooms.every((room) => !room.seatsKnown && !room.seats.length));
  assert.equal(data.currentKnown, false);
  assert.equal(data.scheduledKnown, false);
  assert.equal(data.settings, null);
});

test('층과 예약 조회가 실패해도 열람실과 좌석 현황은 보존한다', async (t) => {
  respond(t, { '/rooms': rooms, '/admin/seats': [
    { seat_id: 3, room_code: 'R1', floor_code: 'F2', seat_number: '1', occupancy_state: 'OCCUPIED' },
  ] });
  const data = await loadAdminData();
  assert.equal(data.rooms[0].seatsKnown, true);
  assert.equal(data.rooms[0].seats[0].seat_id, 3);
  assert.equal(data.currentKnown, false);
});

test('좌석 조회가 실패해도 정상 응답한 설정과 열람실을 보존한다', async (t) => {
  respond(t, { '/rooms': rooms, '/admin/reservation-settings': {
    default_duration_seconds: 3600, max_extensions: 2,
  } });
  const data = await loadAdminData();
  assert.equal(data.roomsKnown, true);
  assert.equal(data.rooms[0].seatsKnown, false);
  assert.deepEqual(data.settings, { duration: 60, maxExtensions: 2 });
});


test('서버가 빈 열람실 목록을 반환하면 기본 열람실을 표시하지 않는다', async (t) => {
  respond(t, { '/rooms': [], '/admin/seats': [] });
  const data = await loadAdminData();
  assert.equal(data.roomsKnown, true);
  assert.deepEqual(data.rooms, []);
});
