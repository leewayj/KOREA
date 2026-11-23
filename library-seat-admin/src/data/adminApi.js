export async function adminRequest(path, { token, method = 'GET', body, signal } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {
    method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json().catch(() => {
    throw new Error('서버 응답을 확인할 수 없습니다.');
  });
  if (!response.ok) {
    throw Object.assign(new Error(result.error?.message || 'API 요청에 실패했습니다.'), { status: response.status });
  }
  return result;
}

async function fetchPages(path, options) {
  const rows = [];
  const limit = 100;
  for (let offset = 0; ; offset += limit) {
    const page = await adminRequest(`${path.includes("?") ? path + "&" : path + "?"}limit=${limit}&offset=${offset}`, options);
    rows.push(...page);
    if (page.length < limit) return rows;
  }
}

export async function loadAdminData(token, signal) {
  const options = { token, signal };
  const results = await Promise.allSettled([
    adminRequest('/floors', options),
    adminRequest('/rooms', options),
    fetchPages('/seats', options),
    fetchPages('/reservations?effective_status=IN_USE', options),
    fetchPages('/reservations?effective_status=SCHEDULED', options),
    adminRequest('/admin/reservation-settings', options),
  ]);
  signal?.throwIfAborted();
  const [floors, rooms, seats, current, scheduled, settings] = results.map(
    (result) => result.status === 'fulfilled' ? result.value : null,
  );
  const floorsById = new Map((floors ?? []).map((floor) => [floor.id, floor]));
  const byLocation = new Map();
  const roomList = (rooms ?? []).map((room) => {
    const floor = floorsById.get(room.floor_id);
    const item = { id: String(room.id), name: floor ? `${room.name} (${floor.name})` : room.name, seats: [] };
    if (floor) byLocation.set(`${floor.code}/${room.code}`, item);
    return item;
  });
  const roomsByCode = new Map();
  for (const room of rooms ?? []) {
    if (!roomsByCode.has(room.code)) roomsByCode.set(room.code, []);
    roomsByCode.get(room.code).push(room);
  }
  const byId = new Map(roomList.map((room) => [room.id, room]));
  const seatsById = new Map();
  for (const seat of seats ?? []) {
    const location = `${seat.floor_code}/${seat.room_code}`;
    let room = byLocation.get(location);
    if (!room && !floors && roomsByCode.get(seat.room_code)?.length === 1) {
      room = byId.get(String(roomsByCode.get(seat.room_code)[0].id));
    }
    if (!room && !rooms) {
      room = { id: encodeURIComponent(location), name: `${seat.room_name} (${seat.floor_name})`, seats: [] };
      roomList.push(room);
    }
    if (!room) continue;
    byLocation.set(location, room);
    room.seats.push(seat);
    seatsById.set(seat.seat_id, { roomId: room.id, seat: seat.seat_number });
  }
  for (const room of roomList) {
    const source = rooms?.find((item) => String(item.id) === room.id);
    room.seatsKnown = seats !== null && !(source && !floors && roomsByCode.get(source.code)?.length > 1);
  }
  return {
    rooms: roomList,
    roomsKnown: rooms !== null,
    currentKnown: current !== null,
    scheduledKnown: scheduled !== null,
    reservations: [...new Map([...(current ?? []), ...(scheduled ?? [])].map((r) => [r.id, r])).values()].flatMap((r) => {
      const seat = seatsById.get(r.seat_id);
      return seat ? [{ ...seat, id: r.id, startsAt: r.starts_at * 1000, endsAt: r.ends_at * 1000, maxExtensions: r.max_extensions }] : [];
    }),
    settings: settings && { duration: settings.default_duration_seconds / 60, maxExtensions: settings.max_extensions },
  };
}
