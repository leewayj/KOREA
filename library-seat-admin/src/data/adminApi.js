export async function adminRequest(path, { token, method = 'GET', body, signal } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`/api${path}`, {
    method, headers, signal, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
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
  const [floors, rooms, seats, reservations, settings] = await Promise.all([
    adminRequest('/floors', options),
    adminRequest('/rooms', options),
    fetchPages('/seats', options),
    fetchPages('/reservations?effective_status=IN_USE', options).then(async (current) =>
      current.concat(await fetchPages('/reservations?effective_status=SCHEDULED', options))),
    adminRequest('/admin/reservation-settings', options),
  ]);
  const floorsById = new Map(floors.map((floor) => [floor.id, floor]));
  const roomsByLocation = new Map();
  const roomList = rooms.map((room) => {
    const floor = floorsById.get(room.floor_id);
    const item = { id: String(room.id), name: `${room.name} (${floor?.name ?? room.floor_id})`, seats: [] };
    roomsByLocation.set(`${floor?.code}/${room.code}`, item);
    return item;
  });

  const seatsById = new Map();
  for (const seat of seats) {
    const room = roomsByLocation.get(`${seat.floor_code}/${seat.room_code}`);
    if (!room) continue;
    room.seats.push(seat);
    seatsById.set(seat.seat_id, { roomId: room.id, seat: seat.seat_number });
  }

  return {
    rooms: roomList,
    reservations: [...new Map(reservations.map((reservation) => [reservation.id, reservation])).values()].flatMap((reservation) => {
      const seat = seatsById.get(reservation.seat_id);
      return seat ? [{
        ...seat,
        id: reservation.id,
        startsAt: reservation.starts_at * 1000,
        endsAt: reservation.ends_at * 1000,
        maxExtensions: reservation.max_extensions,
      }] : [];
    }),
    settings: { duration: settings.default_duration_seconds / 60, maxExtensions: settings.max_extensions },
  };
}
