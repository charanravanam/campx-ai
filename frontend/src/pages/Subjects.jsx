import { useMemo, useState } from "react";
import { api } from "../api.js";
import { useLoad } from "../hooks.js";
import { Card, EmptyState, ErrorState, Notice, PageHead, Skeleton } from "../components/ui.jsx";

export default function Subjects() {
  const { data, error, loading, reload } = useLoad((s) => api.subjects(s));
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    return (data?.subjects || []).filter((s) => !n || [s.subject_code, s.subject_name, s.faculty].some((v) => v?.toLowerCase().includes(n)));
  }, [data, q]);
  return (
    <>
      <PageHead title="Subjects" source={data?.source} />
      {loading ? <Card><Skeleton lines={5} /></Card> : error ? <ErrorState error={error} onRetry={reload} /> :
        !data.subjects.length ? <EmptyState title="No subjects yet" action={{ to: "/settings", label: "Open settings" }}>{data.notice || "Import a timetable or subjects JSON."}</EmptyState> : (
          <>
            {data.notice && <Notice>{data.notice}</Notice>}
            <div className="toolbar">
              <label className="sr" htmlFor="q">Search subjects</label>
              <input id="q" type="search" placeholder="Search by code, name or faculty" value={q} onChange={(e) => setQ(e.target.value)} />
              <span className="muted">{rows.length} of {data.subjects.length}</span>
            </div>
            {rows.length ? (
              <div className="grid">
                {rows.map((s, i) => (
                  <Card key={i} title={s.subject_name || s.subject_code} aside={s.subject_code && s.subject_name ? <span className="code">{s.subject_code}</span> : null}>
                    <dl className="facts compact">
                      <div><dt>Faculty</dt><dd className={s.faculty ? "" : "muted"}>{s.faculty || "Not available"}</dd></div>
                      {s.credits && <div><dt>Credits</dt><dd>{s.credits}</dd></div>}
                      {s.category && <div><dt>Type</dt><dd>{s.category}</dd></div>}
                      {s.semester && <div><dt>Semester</dt><dd>{s.semester}</dd></div>}
                    </dl>
                  </Card>
                ))}
              </div>
            ) : <EmptyState title="No matches">Try a different search.</EmptyState>}
          </>
        )}
    </>
  );
}
