import { useState } from "react";
import { api } from "../api.js";
import { useLoad } from "../hooks.js";
import { Card, EmptyState, ErrorState, Notice, PageHead, Skeleton } from "../components/ui.jsx";

const FIELDS = [
  ["full_name", "Full name"], ["roll_number", "Roll number"], ["email", "Email"], ["branch", "Branch"], ["course", "Course"],
  ["batch", "Batch"], ["semester", "Semester"], ["classroom", "Classroom"], ["section", "Section"],
];

export default function Profile() {
  const { data, error, loading, reload } = useLoad((s) => api.profile(s));
  const [imgBad, setImgBad] = useState(false);
  const p = data?.profile;
  const initials = (p?.full_name || "?").split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  return (
    <>
      <PageHead title="Profile" source={data?.source} />
      {loading ? <Card><Skeleton lines={5} /></Card> : error ? <ErrorState error={error} onRetry={reload} /> :
        !p ? <EmptyState title="No profile data" action={{ to: "/settings", label: "Open settings" }}>{data.notice || "Configure CAMPX_PROFILE_PATH or import a profile JSON."}</EmptyState> : (
          <Card>
            {data.notice && <Notice>{data.notice}</Notice>}
            <div className="profile-top">
              {p.photo_url && !imgBad ? <img className="avatar" src={p.photo_url} alt="" referrerPolicy="no-referrer" onError={() => setImgBad(true)} /> : <div className="avatar avatar-fallback" aria-hidden="true">{initials}</div>}
              <div><h2>{p.full_name || "Name not available"}</h2><p className="muted">{[p.course, p.branch].filter(Boolean).join(" · ")}</p></div>
            </div>
            <dl className="facts">
              {FIELDS.map(([k, label]) => (
                <div key={k}><dt>{label}</dt><dd className={p[k] ? "" : "muted"}>{p[k] || "Not available"}</dd></div>
              ))}
            </dl>
          </Card>
        )}
    </>
  );
}
