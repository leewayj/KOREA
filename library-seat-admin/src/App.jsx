import { useEffect, useRef, useState } from "react";
import { Button } from "./components/Button.jsx";
import InputField from "./components/InputField.jsx";
import {
  MINUTE,
  seatsFor,
  summary,
  remaining,
  progress,
  inputTime,
  parseTime,
  dateTime,
  validateReservation,
  validSettings,
} from "./data/store.js";

import { adminRequest, defaultRoomDirectory, loadAdminData } from "./data/adminApi.js";

const unavailable = "확인할 수 없음";
const loadingData = {
  loading: true, rooms: defaultRoomDirectory, roomsKnown: false, currentKnown: false,
  scheduledKnown: false, reservations: [], settings: null,
};
const titles = {
  home: "도서관 좌석 관리",
  rooms: "예약 데이터 관리",
  create: "가상 예약 등록",
  seat: "좌석 상태",
  edit: "예약 등록·수정",
  settings: "전체 설정",
};
function routeFromHash() {
  const [page = "home", roomId, number] = location.hash
    .replace(/^#\/?/, "")
    .split("/");
  return {
    page: titles[page] ? page : "home",
    roomId,
    number,
  };
}
function Card({ children, className = "" }) {
  return <section className={`card ${className}`}>{children}</section>;
}
function Info({ label, children }) {
  return (
    <div className="info">
      <span>{label}</span>
      <strong>{children}</strong>
    </div>
  );
}
function Bar({ value, round = false }) {
  return (
    <div className={`bar ${round ? "round" : ""}`}>
      <span style={{ width: `${value ?? 0}%` }} />
    </div>
  );
}
function Congestion({ seats, known = true, missing = unavailable }) {
  const s = summary(seats);
  return (
    <div className="congestion">
      <div className="row">
        <strong>현재 혼잡도</strong>
        <span className="badge">
          {!known ? missing : s.rate === null
            ? "확인 불가"
            : s.rate < 50
              ? "여유"
              : s.rate < 80
                ? "보통"
                : "혼잡"}
        </span>
      </div>
      <div className="row">
        <span className="muted small">확인 좌석 기준 이용률</span>
        <strong className="rate">{!known ? "—" : s.rate === null ? "—" : `${s.rate}%`}</strong>
      </div>
      <Bar value={s.rate} round />
      <p className="muted small">
        {known ? `착석 ${s.occupied} / 확인 ${s.known}석 · 미확인 ${s.unknown}석` : `좌석 현황 · ${missing}`}
      </p>
    </div>
  );
}
function Home({ data, now, go }) {
  return (
    <main className="home">
      <div className="home-title">
        <h1>도서관 좌석 관리</h1>
        <button
          className="icon"
          aria-label="전체 설정"
          onClick={() => go("settings")}
        >
          <img src="/assets/settings.svg" alt="" />
        </button>
      </div>
      {!data.roomsKnown && <p className="muted small">
        {data.loading ? "열람실 현황을 불러오는 중입니다." : "열람실 목록을 갱신할 수 없습니다."}
      </p>}
      {data.roomsKnown && !data.rooms.length && <p className="empty">등록된 열람실이 없습니다.</p>}
      {data.rooms.map((room) => {
        const seats = seatsFor(data, room.id, now),
          s = summary(seats);
        return (
          <section className="room-home" key={room.id}>
            <p className="muted">{room.name}</p>
            <button
              className="card room-card"
              onClick={() => go(`rooms/${room.id}`)}
              aria-label={`${room.name} 예약 데이터 관리`}
            >
              <div className="row"><strong>예약 데이터 관리</strong><span aria-hidden="true">›</span></div>
              <Congestion seats={seats} known={room.seatsKnown} missing={data.loading ? "불러오는 중" : unavailable} />
              <div className="stats">
                {[
                  [room.seatsKnown ? seats.length : unavailable, "관리 좌석"],
                  [room.seatsKnown && data.currentKnown ? s.reserved : unavailable, "예약 중"],
                  [room.seatsKnown && data.currentKnown ? s.attention : unavailable, "확인 필요"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <strong className={value === unavailable ? "unknown-value" : undefined}>{value}</strong>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
            </button>
          </section>
        );
      })}
    </main>
  );
}
function RoomPage({ data, room, seats, now, go }) {
  const [filter, setFilter] = useState("all"),
    s = summary(seats);
  const countsKnown = room.seatsKnown && data.currentKnown;
  const groups = [
    ["실제 착석", seats.filter((s) => s.occupied)],
    ["예약 중 · 비착석", seats.filter((s) => s.reservation && !s.occupied)],
    ["예약 없이 착석", seats.filter((s) => s.occupied && !s.reservation)],
    ["상태 미확인", seats.filter((s) => s.unknown)],
  ];
  return (
    <main>
      <h2 className="room-heading">{room.name}</h2>
      <Card>
        <Congestion seats={seats} known={room.seatsKnown} />

        <div className="metrics">
          {groups.map(([label, items], index) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{room.seatsKnown && (data.currentKnown || index === 0 || index === 3) ? `${items.length}석` : unavailable}</strong>
              <small>
                {room.seatsKnown && (data.currentKnown || index === 0 || index === 3) && items.length
                  ? `${items.map((s) => s.number).join(" · ")}번`
                  : "—"}
                {data.currentKnown && label === "예약 없이 착석" && items.length
                  ? " · 예약 없음/만료"
                  : ""}
              </small>
            </div>
          ))}
        </div>
        <p className="muted tiny">
          ※ 예약 없이 착석한 좌석은 실제 착석에 포함됩니다.
        </p>
      </Card>
      <div className="filters">
        {[
          ["all", "전체", seats.length],
          ["reserved", "예약 중", s.reserved],
          ["attention", "확인 필요", s.attention],
        ].map(([key, label, count]) => (
          <Button
            key={key}
            variant={filter === key ? "primary" : "neutral"}
            aria-pressed={filter === key}
            onPress={() => setFilter(key)}
          >
            {label} {(key === "all" ? room.seatsKnown : countsKnown) ? count : "—"}
          </Button>
        ))}
      </div>
      <Button variant="neutral" onPress={() => go(`create/${room.id}`)}>
        가상 예약 등록
      </Button>
      <div className="seat-list">
        {(filter === "all" || countsKnown ? seats : [])
          .filter(
            (s) =>
              filter === "all" ||
              (filter === "reserved" ? s.reservation : s.attention),
          )
          .map((s) => (
            <article className="seat-row" key={s.number}>
              <div className="row">
                <h3>{s.number}번</h3>
                <a
                  href={`#seat/${room.id}/${s.number}`}
                  aria-label={`${s.number}번 상세 보기`}
                >
                  상세 보기
                </a>
              </div>
              <p className={`small ${s.attention ? "danger" : "muted"}`}>
                {data.currentKnown ? s.status : `${s.unknown ? "착석 미확인" : s.occupied ? "착석" : "비착석"} · 예약 ${unavailable}`}
              </p>
              {s.reservation && <Bar value={progress(s.reservation, now)} />}
            </article>
          ))}
        {!room.seatsKnown || (filter !== "all" && !countsKnown) ? <div className="empty">
          <p>좌석 목록 · {unavailable}</p>
          {!room.seatsKnown && <a href={`#seat/${room.id}`}>좌석 상태 보기</a>}
        </div> : !seats.some(
          (s) =>
            filter === "all" ||
            (filter === "reserved" ? s.reservation : s.attention),
        ) && <p className="empty">해당하는 좌석이 없습니다.</p>}
      </div>
    </main>
  );
}
function SeatPage({ data, room, seat, now, go, commit }) {
  if (!seat) return (
    <main className="compact">
      <h2>{room.name} · 좌석 상태</h2>
      <Card><Info label="좌석 번호">{unavailable}</Info><Info label="남은 예약 시간">{unavailable}</Info></Card>
      <Card><h3>좌석 상태</h3>{["최종 상태", "착석 상태", "LED 상태", "센서 상태"].map((label) =>
        <Info key={label} label={label}>{unavailable}</Info>)}</Card>
      <Card><h3>장치의 마지막 적용 응답</h3>{["수신 응답", "장치 통신", "최근 수신"].map((label) =>
        <Info key={label} label={label}>{unavailable}</Info>)}</Card>
      <Button variant="neutral" onPress={() => go(`rooms/${room.id}`)}>좌석 목록 보기</Button>
    </main>
  );
  return <SeatDetails data={data} room={room} seat={seat} now={now} go={go} commit={commit} />;
}
function SeatDetails({ data, room, seat, now, go, commit }) {
  const dialog = useRef(null),
    r = seat.reservation;
  const next = data.reservations
    .filter(
      (x) => x.roomId === room.id && x.seat === seat.number && x.startsAt > now,
    )
    .sort((a, b) => a.startsAt - b.startsAt)[0];
  return (
    <main className="compact">
      <div className="seat-title">
        <h2>{seat.number}번 좌석</h2>
        <span className="badge">
          ● {!data.currentKnown ? unavailable : r ? "예약 중" : seat.unknown ? "확인 불가" : "예약 없음"}
        </span>
      </div>
      <p className="muted subtitle">
        {room.name} · {inputTime(now).slice(0, 10).replaceAll("-", ".")}
      </p>
      <Card>
        <p className="muted subtitle">남은 예약 시간</p>
        <strong className="remaining">
          {r ? `${remaining(r, now)}분` : "—"}
        </strong>
        {r ? (
          <>
            <Bar value={progress(r, now)} />
            <Info label="예약 시간">
              {dateTime(r.startsAt)}–{dateTime(r.endsAt)}
            </Info>
            <Button onPress={() => go(`edit/${room.id}/${seat.number}`)}>
              예약시간 수정
            </Button>
          </>
        ) : (
          <>
            <p className="muted small">{data.currentKnown ? "현재 진행 중인 예약이 없습니다." : `현재 예약 · ${unavailable}`}</p>
            <Button onPress={() => go(`create/${room.id}/${seat.number}`)}>
              가상 예약 등록
            </Button>
          </>
        )}
        {!data.scheduledKnown && <Info label="다음 예약">{unavailable}</Info>}
        {next && !r && (
          <Info label="다음 예약">{dateTime(next.startsAt)} 시작</Info>
        )}
      </Card>
      <Card>
        <h3>좌석 상태</h3>
        <Info label="최종 상태">{data.currentKnown ? seat.status : unavailable}</Info>
        <Info label="착석 상태">
          {seat.unknown ? "확인 불가" : seat.occupied ? "착석 중" : "비착석"}
        </Info>
        <Info label="LED 상태">
          {seat.unknown ? "확인 불가" : seat.occupied ? "소등" : "점등 (시연)"}
        </Info>
        <Info label="센서 상태">시연값 · 실제 센서 미연결</Info>
      </Card>
      <Card>
        <h3 className="device-title">장치의 마지막 적용 응답</h3>
        <Info label="수신 응답">없음 · 실제 장치 미연결</Info>
        <Info label="장치 통신">미연결</Info>
        <Info label="최근 수신">—</Info>
      </Card>
      {r && (
        <Button variant="neutral" onPress={() => dialog.current.showModal()}>
          현재 예약 삭제
        </Button>
      )}
      <dialog
        ref={dialog}
        onClick={(e) => {
          if (e.target === dialog.current) dialog.current.close();
        }}
      >
        <h2>예약을 삭제할까요?</h2>
        <p>{seat.number}번 좌석의 현재 예약이 삭제됩니다.</p>
        <div className="actions">
          <Button
            variant="neutral"
            autoFocus
            onPress={() => dialog.current.close()}
          >
            취소
          </Button>
          <Button
            onPress={async () => {
              if (await commit(
                `/admin/reservations/${r.id}`,
                { method: "DELETE" },
                "예약을 삭제했습니다.",
              )) dialog.current.close();
            }}
          >
            예약 삭제
          </Button>
        </div>
      </dialog>
    </main>
  );
}
function BookingForm({ data, room, seat, edit, now, go, commit }) {
  const original = edit ? seat.reservation : null;
  const [base] = useState(() => Math.floor(Date.now() / MINUTE) * MINUTE);
  const [number, setNumber] = useState(
    seat?.number ?? room.seats[0]?.seat_number ?? "",
  );
  const [studentId, setStudentId] = useState("");
  const [start, setStart] = useState(inputTime(original?.startsAt ?? base));
  const [end, setEnd] = useState(
    inputTime(original?.endsAt ?? (data.settings ? base + data.settings.duration * MINUTE : NaN)),
  );
  const [error, setError] = useState("");
  const startsAt = parseTime(start),
    endsAt = parseTime(end);
  const mins = Number.isFinite(endsAt)
    ? Math.round((endsAt - base) / MINUTE)
    : "";
  const back = () =>
    go(edit ? `seat/${room.id}/${seat.number}` : `rooms/${room.id}`);
  if (edit && !original)
    return (
      <main>
        <h2>{data.currentKnown ? "예약이 종료되었습니다." : `현재 예약 · ${unavailable}`}</h2>
        <p>좌석 상태를 확인하고 새 예약을 등록해주세요.</p>
        <Button onPress={back}>좌석으로 돌아가기</Button>
      </main>
    );
  const next = data.reservations
    .filter(
      (r) =>
        r.roomId === room.id &&
        r.seat === number &&
        r.id !== original?.id &&
        r.startsAt > now,
    )
    .sort((a, b) => a.startsAt - b.startsAt)[0];
  const canSubmit = room.seatsKnown && data.currentKnown && data.scheduledKnown && !!number;
  async function submit(e) {
    e.preventDefault();
    if (!canSubmit) return;
    const candidate = {
      id: original?.id,
      roomId: room.id,
      seat: number,
      startsAt: edit ? original.startsAt : startsAt,
      endsAt,
    };
    const message = validateReservation(data, candidate);
    if (message) {
      setError(message);
      return;
    }
    const times = { starts_at: candidate.startsAt / 1000, ends_at: endsAt / 1000 };
    const seatId = room.seats.find((item) => item.seat_number === number).seat_id;
    const saved = await commit(
      edit ? `/admin/reservations/${original.id}` : "/admin/reservations",
      { method: edit ? "PATCH" : "POST", body: edit ? { ends_at: times.ends_at } : {
        ...times, seat_id: seatId, s_id: studentId,
      } },
      edit ? "예약 시간을 변경했습니다." : "가상 예약을 등록했습니다.",
      setError,
    );
    if (saved) go(`seat/${room.id}/${number}`);
  }
  return (
    <main className={edit ? "compact" : ""}>
      <form onSubmit={submit}>
        <h2>{edit ? `${seat.number}번 좌석` : "예약 정보 입력"}</h2>
        <p className="muted subtitle">
          {room.name}
          {edit ? " · 한국 표준시" : ""}
        </p>
        {edit ? (
          <Card>
            <p className="muted subtitle">현재 남은 시간</p>
            <strong className="current-time">
              {remaining(original, now)}분
            </strong>
            <Info label="현재 종료일시">{dateTime(original.endsAt)}</Info>
          </Card>
        ) : (
          <Card>
            <label>좌석 번호
              <select value={number} onChange={(e) => setNumber(e.target.value)} required>
                {room.seats.map((item) => (
                  <option key={item.seat_id} value={item.seat_number}>{item.seat_number}번</option>
                ))}
              </select>
            </label>
            <InputField label="등록된 학번" value={studentId} onChange={(e) => setStudentId(e.target.value)} />

          </Card>
        )}
        <Card>
          {edit ? (
            <>
              <InputField
                label="변경할 남은 시간 (분)"
                type="number"
                min="1"
                step="1"
                value={mins}
                onChange={(e) =>
                  setEnd(
                    e.target.value === ""
                      ? ""
                      : inputTime(base + Number(e.target.value) * MINUTE),
                  )
                }
              />
              <div className="quick">
                {[-15, 15, 30].map((n) => (
                  <Button
                    key={n}
                    variant="neutral"
                    onPress={() =>
                      setEnd(
                        inputTime(
                          base + Math.max(1, Number(mins) + n) * MINUTE,
                        ),
                      )
                    }
                  >
                    {n < 0 ? "−" : "+"}
                    {Math.abs(n)}분
                  </Button>
                ))}
              </div>
            </>
          ) : (
            <h3>예약 시간</h3>
          )}
          <InputField
            label="예약 시작일시"
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <InputField
            label="예약 종료일시"
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
          {edit ? (
            <p className="muted subtitle">
              종료일시는 시작일시 이후여야 합니다.
              <br />
              같은 좌석의 다른 예약과 겹칠 수 없습니다.
            </p>
          ) : (
            <p className="muted small">
              총 예약 시간{" "}
              {Number.isFinite(endsAt - startsAt)
                ? Math.max(0, Math.round((endsAt - startsAt) / MINUTE))
                : "—"}
              분 · 한국 표준시
            </p>
          )}
        </Card>
        {edit ? (
          <Card>
            <h3>변경 내용</h3>
            <Info label="남은 시간">
              {remaining(original, now)}분 →{" "}
              {Number.isFinite(endsAt)
                ? Math.max(0, Math.ceil((endsAt - now) / MINUTE))
                : "—"}
              분
            </Info>
            <Info label="종료일시">
              {dateTime(original.endsAt)} →{" "}
              {Number.isFinite(endsAt) ? dateTime(endsAt) : "—"}
            </Info>
            <Info label="다음 예약">
              {!data.scheduledKnown ? unavailable : next ? `${dateTime(next.startsAt)} 시작` : "없음"}
            </Info>
          </Card>
        ) : (
          <p className="muted small">
            종료일시는 시작일시 이후여야 하며,
            <br />
            같은 좌석의 기존 예약과 겹칠 수 없어요.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!canSubmit && <p role="status">좌석 또는 예약 정보 · {unavailable}</p>}
        <div className="actions">
          <Button variant="neutral" onPress={back}>
            취소
          </Button>
          <Button type="submit" isDisabled={!canSubmit}>
            {edit ? "변경사항 저장" : "가상 예약 등록"}
          </Button>
        </div>
      </form>
    </main>
  );
}
function Settings({ data, commit }) {
  const [duration, setDuration] = useState(String(data.settings?.duration ?? "")),
    [limit, setLimit] = useState(String(data.settings?.maxExtensions ?? "")),
    [error, setError] = useState("");
  return (
    <main className="compact">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const settings = {
            duration: Number(duration),
            maxExtensions: Number(limit),
          };
          if (!duration || !limit || !validSettings(settings)) {
            setError(
              "예약 시간은 1~1440분, 연장 횟수는 0~100의 정수로 입력하세요.",
            );
            return;
          }
          setError("");
          commit(
            "/admin/reservation-settings",
            { method: "PATCH", body: {
              default_duration_seconds: settings.duration * 60,
              max_extensions: settings.maxExtensions,
            } },
            "설정을 저장했습니다. 새 예약부터 적용됩니다.",
            setError,
          );
        }}
      >
        <h2>예약 운영 설정</h2>
        <Card>
          <InputField
            label="기본 예약 시간(분)"
            type="number"
            min="1"
            max="1440"
            step="1"
            disabled={!data.settings}
            placeholder={data.loading ? "불러오는 중" : unavailable}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
          />
        </Card>
        <Card>
          <h3>예약 연장 제한</h3>
          <InputField
            label="최대 연장 횟수"
            type="number"
            min="0"
            max="100"
            step="1"
            disabled={!data.settings}
            placeholder={data.loading ? "불러오는 중" : unavailable}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </Card>
        <aside className="settings-note">
          <strong>설정 적용 안내</strong>
          <p>
            변경한 설정은 새 예약부터 적용됩니다.
            <br />
            이미 진행 중인 예약은 기존 설정을 유지합니다.
          </p>
        </aside>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <Button type="submit" isDisabled={!data.settings}>설정 저장</Button>
      </form>
    </main>
  );
}
export default function App() {
  const [data, setData] = useState(loadingData),
    [error, setError] = useState(""),
    pending = useRef(false),
    [route, setRoute] = useState(routeFromHash),
    [now, setNow] = useState(Date.now),
    [notice, setNotice] = useState("");
  const { page, roomId, number } = route,
    room = data?.rooms.find((r) => r.id === roomId),
    seats = room ? seatsFor(data, roomId, now) : [],
    seat = seats.find((s) => s.number === number);
  const go = (path) => {
    location.hash = path;
  };
  useEffect(() => {
    const update = () => setRoute(routeFromHash());
    window.addEventListener("hashchange", update);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.removeEventListener("hashchange", update);
      clearInterval(tick);
    };
  }, []);
  useEffect(() => {
    document.title = `${titles[page]} · 관리자`;
    window.scrollTo(0, 0);
  }, [page, roomId, number]);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    const controller = new AbortController();
    let loading = false;
    async function refresh() {
      if (loading || pending.current) return;
      loading = true;
      try {
        const next = await loadAdminData(undefined, controller.signal);
        if (!controller.signal.aborted && !pending.current) {
          setData(next);
          setError("");
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        setError(error.message);
      } finally {
        loading = false;
      }
    }
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  async function commit(path, options, message, showError = setError) {
    if (pending.current) return false;
    pending.current = true;
    try {
      await adminRequest(path, options);
    } catch (error) {
      showError(error.message);
      pending.current = false;
      return false;
    }
    try {
      setData(await loadAdminData());
      setNotice(message);
    } catch {
      setNotice(`${message} 목록을 다시 불러오는 중입니다.`);
    } finally {
      pending.current = false;
    }
    return true;
  }

  const invalidRoute = !["home", "settings"].includes(page) &&
    (!room || (!seat && (page === "edit" || (page === "seat" && room.seatsKnown && number))));
  const back = () =>
    go(
      page === "rooms" || page === "settings"
        ? "home"
        : page === "edit"
          ? `seat/${roomId}/${number}`
          : `rooms/${roomId}`,
    );
  return (
    <div className="app-shell">
      {page !== "home" && (
        <header>
          <button className="icon back" aria-label="뒤로 가기" onClick={back}>
            <img src={`/assets/${page}-back.svg`} alt="" />
          </button>
          <h1>{titles[page]}</h1>
        </header>
      )}
      {error && <p role="alert">{error}</p>}
      {invalidRoute ? (
        <main><p>{data.loading ? "불러오는 중" : (!room ? !data.roomsKnown : !room.seatsKnown) ? `열람실 또는 좌석 정보 · ${unavailable}` : "해당 열람실 또는 좌석을 찾을 수 없습니다."}</p><Button onPress={() => go("home")}>홈으로</Button></main>
      ) : page === "home" ? (
        <Home data={data} now={now} go={go} />
      ) : page === "rooms" ? (
        <RoomPage
          key={roomId}
          data={data}
          room={room}
          seats={seats}
          now={now}
          go={go}
        />
      ) : page === "seat" ? (
        <SeatPage
          data={data}
          room={room}
          seat={seat}
          now={now}
          go={go}
          commit={commit}
        />
      ) : page === "settings" ? (
        <Settings key={Boolean(data.settings)} data={data} commit={commit} />
      ) : (
        <BookingForm
          key={`${page}/${roomId}/${number}`}
          data={data}
          room={room}
          seat={seat}
          edit={page === "edit"}
          now={now}
          go={go}
          commit={commit}
        />
      )}
      <div role="status" className={`toast ${notice ? "visible" : ""}`}>
        {notice}
      </div>
    </div>
  );
}
