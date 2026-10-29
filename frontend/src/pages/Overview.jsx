import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useLoad } from "../hooks.js";
import { Card, EmptyState, ErrorState, PageHead, Skeleton, SourceBadge, fmtTime } from "../components/ui.jsx";

function ClassRow({ e, tag }) {
  return (
    <li className="slot">
      <div className="slot-time">{fmtTime(e.start)}<span>{fmtTime(e.end)}</span></div>
      <div className="slot-body">
        <strong>{e.subject_name || e.subject_code}</strong>
        <span className="muted">{[e.room, e.faculty].filter(Boolean).join(" · ") || "Room / faculty not listed"}</span>
      </div>
      {tag && <span className="tag">{tag}</span>}
    </li>
  );
}

export default function Overview() {
  const profile = useLoad((s) => api.profile(s));
  const today = useLoad((s) => api.today(s));
  const subjects = useLoad((s) => api.subjects(s));
  const att = useLoad((s) => api.attendance(75, s));

  const p = profile.data?.profile;
  const t = today.data;
  return (
    <>
      <PageHead title={p?.full_name ? `Hello, ${p.full_name.split(" ")[0]}` : "Overview"} sub={p?.branch || (t && `${t.day}`)} />
      <div className="grid">
        <Card title="Next class" className="span-2 hero">
          {today.loading ? <Skeleton lines={2} height={22} /> : today.error ? <ErrorState error={today.error} onRetry={today.reload} /> :
            t.next_class || t.current_class ? (
              <>
                {t.current_class && <><p className="muted">In progress</p><ul className="slots"><ClassRow e={t.current_class} tag="Now" /></ul></>}
                {t.next_class && <><p className="muted">Up next</p><ul className="slots"><ClassRow e={t.next_class} /></ul></>}
              </>
            ) : <EmptyState title={t.class_count ? "No more classes today" : t.source === "none" ? "No timetable yet" : `No classes on ${t.day}`} action={t.source === "none" ? { to: "/settings", label: "Set up timetable" } : null}>
              {t.notice}</EmptyState>}
        </Card>

        <Card title="Today" aside={<SourceBadge source={t?.source} />}>
          {today.loading ? <Skeleton /> : today.error ? null : (
            <>
              <p className="big">{t.class_count}</p>
              <p className="muted">class{t.class_count === 1 ? "" : "es"} on {t.day}</p>
            </>
          )}
        </Card>

        <Card title="Subjects" aside={<SourceBadge source={subjects.data?.source} />}>
          {subjects.loading ? <Skeleton /> : subjects.error ? <p className="muted">Unavailable</p> : (
            <>
              <p className="big">{subjects.data.subjects.length || "—"}</p>
              <p className="muted">{subjects.data.subjects.length ? <Link to="/subjects">View subjects</Link> : "No subject data yet"}</p>
            </>
          )}
        </Card>

        <Card title="Attendance" aside={<SourceBadge source={att.data?.source} />}>
          {att.loading ? <Skeleton /> : att.error ? <p className="muted">Unavailable</p> : att.data.overall ? (
            <>
              <p className={`big ${att.data.overall.status === "low" ? "low" : ""}`}>{att.data.overall.percentage}%</p>
              <p className="muted">{att.data.overall.attended} of {att.data.overall.total} classes · <Link to="/attendance">Details</Link></p>
            </>
          ) : <p className="muted">No attendance data yet. <Link to="/settings">Import attendance</Link></p>}
        </Card>

        <Card title="Later today" className="span-2">
          {today.loading ? <Skeleton /> : today.error ? null : t.upcoming.length > (t.next_class ? 1 : 0) ? (
            <ul className="slots">{t.upcoming.slice(t.next_class ? 1 : 0).map((e, i) => <ClassRow key={i} e={e} />)}</ul>
          ) : <p className="muted">Nothing else scheduled.</p>}
        </Card>
      </div>
    </>
  );
}
