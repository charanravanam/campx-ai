import { Link } from "react-router-dom";

export const SOURCE_LABEL = {
  campx: "Live CampX",
  imported: "Imported JSON",
  derived: "Derived",
  none: "No data",
};

export function SourceBadge({ source }) {
  if (!source) return null;
  return <span className={`badge badge-${source}`}>{SOURCE_LABEL[source] || source}</span>;
}

export function Skeleton({ lines = 3, height = 16 }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="sk-line" style={{ height, width: `${100 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function Notice({ children, tone = "info" }) {
  return <div className={`notice notice-${tone}`} role={tone === "error" ? "alert" : "status"}>{children}</div>;
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <Link className="btn btn-quiet" to={action.to}>{action.label}</Link>}
    </div>
  );
}

const HINTS = {
  not_configured: "This live endpoint is not configured. Import a JSON file in Settings, or configure the path in .env.",
  upstream_forbidden: "CampX refused this request. See Troubleshooting in the README.",
  upstream_not_found: "The configured CampX path does not exist. Re-check it with DevTools.",
  unsupported_structure: "CampX returned data in a shape the app does not recognise yet. Share a redacted sample to extend the normalizer.",
};

export function ErrorState({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="empty empty-error" role="alert">
      <h3>{error.message}</h3>
      {HINTS[error.code] && <p>{HINTS[error.code]}</p>}
      <p className="muted">Error code: <code>{error.code}</code></p>
      {onRetry && <button className="btn btn-quiet" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function Card({ title, aside, children, className = "" }) {
  return (
    <section className={`card ${className}`}>
      {(title || aside) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHead({ title, sub, source }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <p className="muted">{sub}</p>}
      </div>
      <SourceBadge source={source} />
    </div>
  );
}

export const fmtTime = (t) => {
  if (!t) return "—";
  const [h, m] = t.split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h >= 12 ? "pm" : "am"}`;
};
