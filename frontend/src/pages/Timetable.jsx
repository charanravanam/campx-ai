import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { useLoad } from "../hooks.js";
import { Card, EmptyState, ErrorState, Notice, PageHead, Skeleton, fmtTime } from "../components/ui.jsx";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const todayName = () => DAYS[(new Date().getDay() + 6) % 7];

function Period({ e }) {
  if (e.kind === "break") return <li className="period period-break"><time>{fmtTime(e.start)}</time><span>Break</span></li>;
  if (e.kind === "free") return <li className="period period-free"><time>{fmtTime(e.start)}</time><span>No class scheduled</span></li>;
  return (
    <li className="period">
      <time>{fmtTime(e.start)}<span>{fmtTime(e.end)}</span></time>
      <div>
        <strong>{e.subject_name || e.subject_code}</strong>
        {e.subject_name && e.subject_code && <span className="code">{e.subject_code}</span>}
        <div className="muted">{[e.room && `Room ${e.room}`, e.faculty].filter(Boolean).join(" · ") || "Room / faculty not listed"}</div>
      </div>
    </li>
  );
}

export default function Timetable() {
  const { data, error, loading, reload } = useLoad((s) => api.timetable(s));
  const [view, setView] = useState("day");
  const [day, setDay] = useState(todayName());
  const days = useMemo(() => DAYS.filter((d) => data?.entries.some((e) => e.day === d)), [data]);
  useEffect(() => { if (days.length && !days.includes(day)) setDay(days[0]); }, [days, day]);
  const by = (d) => data.entries.filter((e) => e.day === d);
  const today = todayName();

  return (
    <>
      <PageHead title="Timetable" source={data?.source} />
      {loading ? <Card><Skeleton lines={6} height={20} /></Card> : error ? <ErrorState error={error} onRetry={reload} /> :
        !data.entries.length ? <EmptyState title="No timetable yet" action={{ to: "/settings", label: "Open settings" }}>{data.notice || "Nothing to show."}</EmptyState> : (
          <>
            {data.notice && <Notice>{data.notice}</Notice>}
            <div className="toolbar">
              <div className="seg" role="group" aria-label="View">
                <button className={view === "day" ? "on" : ""} aria-pressed={view === "day"} onClick={() => setView("day")}>Day</button>
                <button className={view === "week" ? "on" : ""} aria-pressed={view === "week"} onClick={() => setView("week")}>Week</button>
              </div>
              {view === "day" && (
                <div className="tabs" role="tablist" aria-label="Day">
                  {days.map((d) => (
                    <button key={d} role="tab" aria-selected={d === day} className={d === day ? "on" : ""} onClick={() => setDay(d)}>
                      {d.slice(0, 3)}{d === today && <i className="dot" title="Today" />}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {view === "day" ? (
              <Card title={day} aside={day === today ? <span className="tag">Today</span> : null}>
                <ul className="periods">{by(day).map((e, i) => <Period key={i} e={e} />)}</ul>
              </Card>
            ) : (
              <div className="week">
                {days.map((d) => (
                  <Card key={d} title={d} aside={d === today ? <span className="tag">Today</span> : null} className={d === today ? "is-today" : ""}>
                    <ul className="periods">{by(d).map((e, i) => <Period key={i} e={e} />)}</ul>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}
    </>
  );
}
