import { useEffect, useRef, useState } from "react";
import { Button } from "./components/Button.jsx";
import InputField from "./components/InputField.jsx";
import {
  MINUTE,
  rooms,
  storageKey,
  loadData,
  seatsFor,
  summary,
  remaining,
  progress,
  inputTime,
  parseTime,
  dateTime,
  validateReservation,
  saveReservation,
  validSettings,
} from "./data/store.js";

const titles = {
  home: "도서관 좌석 관리",
  rooms: "예약 데이터 관리",
  create: "가상 예약 등록",
  seat: "좌석 상태",
  edit: "예약 등록·수정",
  settings: "전체 설정",
};
function routeFromHash() {
  const [page = "home", roomId = "reading-2", number = "66"] = location.hash
    .replace(/^#\/?/, "")
    .split("/");
  return {
    page: titles[page] ? page : "home",
    roomId: rooms.some((r) => r.id === roomId) ? roomId : "reading-2",
    number: [66, 67, 68, 69, 70, 71].includes(Number(number))
      ? Number(number)
      : 66,
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
function Congestion({ seats }) {
  const s = summary(seats);
  return (
    <div className="congestion">
      <div className="row">
        <strong>현재 혼잡도</strong>
        <span className="badge">
          {s.rate === null
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
        <strong className="rate">{s.rate === null ? "—" : `${s.rate}%`}</strong>
      </div>
      <Bar value={s.rate} round />
      <p className="muted small">
        착석 {s.occupied} / 확인 {s.known}석 · 미확인 {s.unknown}석
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
      {rooms.map((room) => {
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
              <Congestion seats={seats} />
              <div className="stats">
                {[
                  [6, "관리 좌석"],
                  [s.reserved, "예약 중"],
                  [s.attention, "확인 필요"],
                ].map(([value, label]) => (
                  <div key={label}>
                    <strong>{value}</strong>
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
function RoomPage({ room, seats, now, go }) {
  const [filter, setFilter] = useState("all"),
    s = summary(seats);
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
        <Congestion seats={seats} />
        <p className="muted tiny">시연 데이터 · 실제 센서 미연결</p>
        <div className="metrics">
          {groups.map(([label, items]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{items.length}석</strong>
              <small>
                {items.length
                  ? `${items.map((s) => s.number).join(" · ")}번`
                  : "—"}
                {label === "예약 없이 착석" && items.length
                  ? " · 예약 없음/만료"
                  : ""}
              </small>
            </div>
          ))}
        </div>
        <p className="muted tiny">
          ※ 예약 없이 착석한 좌석은 실제 착석에 포함됩니다.
        </p>
        <div className="help tiny">
          <p>
            미확인 좌석은 이용률 계산에서 제외해요.
            <br />
            전체 미확인 시 ‘확인 불가’로 표시해요.
          </p>
          <p>
            기준: 여유 &lt;50% · 보통 50% 이상~80% 미만
            <br />
            혼잡 ≥80% (확인 좌석 기준)
          </p>
        </div>
      </Card>
      <div className="filters">
        {[
          ["all", "전체", 6],
          ["reserved", "예약 중", s.reserved],
          ["attention", "확인 필요", s.attention],
        ].map(([key, label, count]) => (
          <Button
            key={key}
            variant={filter === key ? "primary" : "neutral"}
            aria-pressed={filter === key}
            onPress={() => setFilter(key)}
          >
            {label} {count}
          </Button>
        ))}
      </div>
      <Button variant="neutral" onPress={() => go(`create/${room.id}`)}>
        가상 예약 등록
      </Button>
      <div className="seat-list">
        {seats
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
                {s.status}
              </p>
              {s.reservation && <Bar value={progress(s.reservation, now)} />}
            </article>
          ))}
        {!seats.some(
          (s) =>
            filter === "all" ||
            (filter === "reserved" ? s.reservation : s.attention),
        ) && <p className="empty">해당하는 좌석이 없습니다.</p>}
      </div>
    </main>
  );
}
function SeatPage({ data, room, seat, now, go, commit }) {
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
          ● {r ? "예약 중" : seat.unknown ? "확인 불가" : "예약 없음"}
        </span>
      </div>
      <p className="muted subtitle">
        {room.name} · {inputTime(now).slice(0, 10).replaceAll("-", ".")} · 가상
        데이터
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
            <p className="muted small">현재 진행 중인 예약이 없습니다.</p>
            <Button onPress={() => go(`create/${room.id}/${seat.number}`)}>
              가상 예약 등록
            </Button>
          </>
        )}
        {next && !r && (
          <Info label="다음 예약">{dateTime(next.startsAt)} 시작</Info>
        )}
      </Card>
      <Card>
        <h3>좌석 상태</h3>
        <Info label="최종 상태">{seat.status}</Info>
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
            onPress={() => {
              commit(
                {
                  ...data,
                  reservations: data.reservations.filter((x) => x.id !== r.id),
                },
                "예약을 삭제했습니다.",
              );
              dialog.current.close();
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
    edit ? seat.number : seat.reservation ? 67 : seat.number,
  );
  const [start, setStart] = useState(inputTime(original?.startsAt ?? base));
  const [end, setEnd] = useState(
    inputTime(original?.endsAt ?? base + data.settings.duration * MINUTE),
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
        <h2>예약이 종료되었습니다.</h2>
        <p>좌석 상태를 확인하고 새 예약을 등록해주세요.</p>
        <Button onPress={back}>좌석으로 돌아가기</Button>
      </main>
    );
  const next = data.reservations
    .filter(
      (r) =>
        r.roomId === room.id &&
        r.seat === Number(number) &&
        r.id !== original?.id &&
        r.startsAt > now,
    )
    .sort((a, b) => a.startsAt - b.startsAt)[0];
  function submit(e) {
    e.preventDefault();
    const candidate = {
      id: original?.id,
      roomId: room.id,
      seat: Number(number),
      startsAt,
      endsAt,
    };
    const message = validateReservation(data, candidate);
    if (message) {
      setError(message);
      return;
    }
    commit(
      saveReservation(data, candidate),
      edit ? "예약 시간을 변경했습니다." : "가상 예약을 등록했습니다.",
    );
    go(`seat/${room.id}/${number}`);
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
            <InputField
              label="좌석 번호"
              type="number"
              min="66"
              max="71"
              step="1"
              value={number}
              onChange={(e) => setNumber(e.target.value)}
            />
            <p className="muted small">
              현재 열람실의 좌석 번호를 입력하세요. (66~71)
            </p>
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
              {next ? `${dateTime(next.startsAt)} 시작` : "없음"}
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
        <div className="actions">
          <Button variant="neutral" onPress={back}>
            취소
          </Button>
          <Button type="submit">
            {edit ? "변경사항 저장" : "가상 예약 등록"}
          </Button>
        </div>
      </form>
    </main>
  );
}
function Settings({ data, commit }) {
  const [duration, setDuration] = useState(String(data.settings.duration)),
    [limit, setLimit] = useState(String(data.settings.maxExtensions)),
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
            { ...data, settings },
            "설정을 저장했습니다. 새 예약부터 적용됩니다.",
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
        <Button type="submit">설정 저장</Button>
      </form>
    </main>
  );
}
export default function App() {
  const [data, setData] = useState(loadData),
    [route, setRoute] = useState(routeFromHash),
    [now, setNow] = useState(Date.now),
    [notice, setNotice] = useState("");
  const { page, roomId, number } = route,
    room = rooms.find((r) => r.id === roomId),
    seats = seatsFor(data, roomId, now),
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
  function commit(next, message) {
    setData(next);
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
      setNotice(message);
    } catch {
      setNotice(
        `${message} 브라우저 저장 공간을 사용할 수 없어 새로고침하면 초기화됩니다.`,
      );
    }
  }
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
      {page === "home" ? (
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
        <Settings data={data} commit={commit} />
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
