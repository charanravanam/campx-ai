import { useRef, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Card, Notice, PageHead } from "../components/ui.jsx";

const MODE_HELP = {
  auto: "Tries live CampX first, then falls back to JSON you imported.",
  campx: "Live CampX only. Missing endpoints show an error.",
  imported: "Only JSON you imported. CampX is not used for data.",
};
const KINDS = [["timetable", "Timetable"], ["attendance", "Attendance"], ["profile", "Profile"], ["subjects", "Subjects"]];

function ImportRow({ kind, label, when, onChange }) {
  const ref = useRef(null);
  const [msg, setMsg] = useState(null);
  async function pick(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setMsg(null);
    if (file.size > 256 * 1024) return setMsg({ tone: "error", text: "File is larger than 256 KB." });
    try {
      const out = await api.importJson(kind, await file.text());
      setMsg({ tone: "ok", text: `Imported ${out.count} item${out.count === 1 ? "" : "s"}.` });
      onChange();
    } catch (err) { setMsg({ tone: "error", text: err.message }); }
  }
  async function remove() {
    try { await api.deleteImport(kind); setMsg({ tone: "ok", text: "Removed." }); onChange(); } catch (err) { setMsg({ tone: "error", text: err.message }); }
  }
  return (
    <li className="import-row">
      <div><strong>{label}</strong><div className="muted">{when ? `Imported ${new Date(when).toLocaleString()}` : "Nothing imported"}</div></div>
      <div className="row-actions">
        <input ref={ref} type="file" accept="application/json,.json" hidden onChange={pick} aria-label={`Choose ${label} JSON file`} />
        <button className="btn btn-quiet" onClick={() => ref.current.click()}>Choose JSON…</button>
        {when && <button className="btn btn-quiet" onClick={remove}>Remove</button>}
      </div>
      {msg && <p className={msg.tone === "error" ? "field-error" : "ok-text"} role="status">{msg.text}</p>}
    </li>
  );
}

export default function Settings() {
  const { me, logout, refresh } = useAuth();
  const live = me.live_endpoints;
  return (
    <>
      <PageHead title="Settings" />
      <div className="grid">
        <Card title="Data source">
          <p className="big sm">{me.data_source}</p>
          <p className="muted">{MODE_HELP[me.data_source]}</p>
          <p className="muted">Change it with <code>DATA_SOURCE</code> in <code>.env</code>, then restart the backend.</p>
        </Card>
        <Card title="Connection">
          <ul className="status-list">
            <li><span className="ok-dot" /> Signed in as {me.user.login_hint} ({me.user.tenant})</li>
            <li>Session ends {new Date(me.expires_at).toLocaleString()}</li>
            {["profile", "timetable", "attendance", "subjects"].map((k) => (
              <li key={k}><span className={live[k] ? "ok-dot" : "off-dot"} /> Live {k}: {live[k] ? "path configured (not guaranteed to work)" : "not configured"}</li>
            ))}
          </ul>
        </Card>
        <Card title="Import your own JSON" className="span-2">
          <Notice>Imported files belong to your account only. Only synthetic or your own data - never someone else's records.</Notice>
          <ul className="imports">
            {KINDS.map(([k, l]) => <ImportRow key={k} kind={k} label={l} when={me.imports?.[k]} onChange={refresh} />)}
          </ul>
        </Card>
        <Card title="Sign out" className="span-2">
          <p className="muted">Ends your CampX AI session on the server and clears the cookie.</p>
          <button className="btn btn-danger" onClick={logout}>Log out</button>
        </Card>
      </div>
    </>
  );
}
