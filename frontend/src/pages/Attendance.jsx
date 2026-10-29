import { useCallback, useMemo, useState } from "react";
import { api } from "../api.js";
import { useDebounced, useLoad } from "../hooks.js";
import { Card, EmptyState, ErrorState, Notice, PageHead, Skeleton, fmtTime } from "../components/ui.jsx";

const pct = (v) => (v == null ? "—" : `${v}%`);
const dateLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

function Bar({ value, status, label }) {
  return (
    <div className="bar" role="img" aria-label={label}>
      <div className={`bar-fill ${status}`} style={{ width: `${Math.min(100, value ?? 0)}%` }} />
    </div>
  );
}

function Recovery({ row, target }) {
  const r = row.recovery;
  switch (r.state) {
    case "already_met":
      return <p className="ok-text">At or above {target}%. You can miss up to <strong>{row.classes_can_miss}</strong> more class{row.classes_can_miss === 1 ? "" : "es"} and stay there.</p>;
    case "date":
      return <p className="low-text">Attend the next <strong>{r.needed}</strong> class{r.needed === 1 ? "" : "es"} in a row. By your timetable you reach {target}% on <strong>{dateLabel(r.date)}</strong>.</p>;
    case "insufficient_sessions":
      return <p className="low-text">You need <strong>{r.needed}</strong> more class{r.needed === 1 ? "" : "es"} in a row, but only {r.available_units} upcoming session{r.available_units === 1 ? "" : "s"} are listed, so no recovery date can be estimated.</p>;
    case "no_timetable":
      return <p className="low-text">You need <strong>{r.needed}</strong> more class{r.needed === 1 ? "" : "es"} in a row. No dated timetable is available, so a recovery date cannot be estimated.</p>;
    case "no_counts":
      return <p className="muted">No class counts in the source, so no projection.</p>;
    default:
      return <p className="muted">No classes conducted yet; nothing to forecast.</p>;
  }
}

function Scenario({ row, target, labUnits }) {
  const [attend, setAttend] = useState(0);
  const [miss, setMiss] = useState(0);
  const [out, setOut] = useState(null);
  const [err, setErr] = useState(null);
  const run = async () => {
    setErr(null);
    try { setOut(await api.scenario({ subject_key: row.subject_key, target, attend, miss }, labUnits)); }
    catch (e) { setErr(e.message); }
  };
  const num = (set) => (e) => { set(Math.max(0, Math.min(1000, Number(e.target.value) || 0))); setOut(null); };
  return (
    <div className="scenario">
      <h3>What if…</h3>
      <div className="scenario-row">
        <label>Attend <input type="number" inputMode="numeric" min="0" max="1000" value={attend} onChange={num(setAttend)} /></label>
        <label>Miss <input type="number" inputMode="numeric" min="0" max="1000" value={miss} onChange={num(setMiss)} /></label>
        <button className="btn btn-quiet" onClick={run}>Calculate</button>
      </div>
      {err && <p className="field-error" role="alert">{err}</p>}
      {out && (
        <p role="status">
          Projected: <strong>{pct(out.projected.percentage)}</strong> ({out.projected.attended} of {out.projected.total}).{" "}
          {out.meets_target ? "Meets" : "Below"} {out.target}%. <span className="muted">Hypothetical only. Nothing is saved.</span>
        </p>
      )}
    </div>
  );
}

function Subject({ row, target, labUnits, enabled, busy, onMark, onReset }) {
  const [open, setOpen] = useState(false);
  const sim = row.simulated;
  if (!sim) {
    return (
      <Card title={row.subject_name || row.subject_code}>
        <p className="muted">{row.notes?.[0] || "No class counts available."}</p>
        <span className="badge">{row.source_label}</span>
      </Card>
    );
  }
  return (
    <Card title={row.subject_name || row.subject_code} aside={row.subject_code && row.subject_name ? <span className="code">{row.subject_code}</span> : null} className="subj">
      <div className="overall-row">
        <p className={`big sm ${row.status}`}>{pct(sim.percentage)}</p>
        <div>
          <p>{sim.attended} attended · {sim.missed} missed · {sim.total} conducted</p>
          <span className={`badge ${row.has_simulation ? "badge-sim" : "badge-imported"}`}>{sim.source_label}</span>
        </div>
      </div>
      <Bar value={sim.percentage} status={row.status} label={`${row.subject_name}: ${pct(sim.percentage)} attendance, target ${target}%`} />
      <Recovery row={row} target={target} />
      {row.has_simulation && (
        <p className="muted">Imported baseline: {row.baseline.attended} of {row.baseline.total} ({pct(row.baseline.percentage)}). Simulated values are not official records.</p>
      )}
      <button className="btn btn-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide details" : "Details & simulation"}</button>
      {open && (
        <div className="subj-detail">
          {row.notes.map((n, i) => <Notice key={i} tone="warn">{n}</Notice>)}
          <h3>Upcoming sessions</h3>
          {!row.upcoming.length ? <p className="muted">No upcoming sessions found in the timetable.</p> : (
            <ul className="sessions">
              {row.upcoming.map((s) => (
                <li key={s.session_key}>
                  <div>
                    <strong>{dateLabel(s.date)}</strong> <span className="muted">{fmtTime(s.start)}</span>
                    {s.kind === "lab" && <span className="tag"> Lab{s.period_count > 1 ? ` · ${s.period_count} periods` : ""}</span>}
                    {s.groups.length > 0 && <span className="muted"> · {s.groups.join(", ")}</span>}
                  </div>
                  {enabled ? (
                    <div className="seg" role="group" aria-label={`Outcome for ${dateLabel(s.date)}`}>
                      {["present", "absent"].map((st) => (
                        <button key={st} className={s.simulated_status === st ? "on" : ""} aria-pressed={s.simulated_status === st} disabled={busy}
                          onClick={() => (s.simulated_status === st ? onReset(s.session_key) : onMark(row.subject_key, s.session_key, st))}>
                          {st === "present" ? "Present" : "Absent"}
                        </button>
                      ))}
                    </div>
                  ) : <span className="muted">Read-only</span>}
                </li>
              ))}
            </ul>
          )}
          {row.has_simulation && <button className="btn btn-quiet" disabled={busy} onClick={() => onReset(null, row.subject_key)}>Reset this subject</button>}
          <Scenario row={row} target={target} labUnits={labUnits} />
        </div>
      )}
    </Card>
  );
}

export default function Attendance() {
  const [target, setTarget] = useState(75);
  const [labUnits, setLabUnits] = useState("session");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const t = useDebounced(target, 250);
  const { data, error, loading, reload } = useLoad((s) => api.forecast(t, labUnits, s), [t, labUnits]);

  const act = useCallback(async (fn) => {
    setBusy(true); setActionError(null);
    try { await fn(); reload(); } catch (e) { setActionError(e.message); } finally { setBusy(false); }
  }, [reload]);
  const onMark = useCallback((subj, sk, status) => act(() => api.setAdjustment(subj, sk, status)), [act]);
  const onReset = useCallback((sk, subj) => act(() => (sk ? api.clearSession(sk) : api.resetAdjustments(subj))), [act]);
  const anySim = useMemo(() => data?.subjects?.some((s) => s.has_simulation), [data]);

  return (
    <>
      <PageHead title="Attendance" source={data?.source} />
      <Card className="target">
        <label htmlFor="target">Target attendance: <strong>{target}%</strong></label>
        <input id="target" type="range" min="50" max="95" step="1" value={target} onChange={(e) => setTarget(Number(e.target.value))} />
        <div className="toolbar">
          <label htmlFor="labu" className="muted">Count multi-period labs as</label>
          <select id="labu" value={labUnits} onChange={(e) => setLabUnits(e.target.value)}>
            <option value="session">one class (default)</option>
            <option value="period">one class per period</option>
          </select>
        </div>
        <p className="muted">Calculated from exact class counts. Projections assume you attend every class from now on. Your institution&apos;s minimum may differ.</p>
      </Card>
      {actionError && <Notice tone="error">{actionError}</Notice>}
      {loading && !data ? <Card><Skeleton lines={5} /></Card> : error ? <ErrorState error={error} onRetry={reload} /> :
        !data.subjects.length ? <EmptyState title="No attendance data" action={{ to: "/settings", label: "Import attendance" }}>{data.notice || "Import an attendance JSON file in Settings."}</EmptyState> : (
          <>
            {data.notice && <Notice>{data.notice}</Notice>}
            {data.overall && (
              <Card title="Overall" className="overall">
                <div className="overall-row">
                  <p className={`big ${data.overall.status}`}>{pct(data.overall.percentage)}</p>
                  <p>{data.overall.attended} attended of {data.overall.total} across {data.overall.subjects_counted} subject{data.overall.subjects_counted === 1 ? "" : "s"}</p>
                </div>
                <Bar value={data.overall.percentage} status={data.overall.status} label={`Overall ${pct(data.overall.percentage)}`} />
              </Card>
            )}
            {anySim && <Notice tone="warn">Some figures include your simulated outcomes. <button className="btn btn-quiet" disabled={busy} onClick={() => act(() => api.resetAdjustments())}>Reset all simulations</button></Notice>}
            <div className="grid">
              {data.subjects.map((r) => (
                <Subject key={r.subject_key} row={r} target={data.target} labUnits={labUnits} enabled={data.adjustments_enabled} busy={busy} onMark={onMark} onReset={onReset} />
              ))}
            </div>
          </>
        )}
    </>
  );
}
