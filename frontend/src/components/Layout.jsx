import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";

const NAV = [
  ["/", "Overview", "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"],
  ["/timetable", "Timetable", "M7 3v3M17 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"],
  ["/attendance", "Attendance", "M4 20V10M10 20V4M16 20v-7M22 20H2"],
  ["/subjects", "Subjects", "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11"],
  ["/profile", "Profile", "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0"],
  ["/settings", "Settings", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12l2-1-2-4-2 .5-1.5-1L15 4h-4l-.5 2.5-1.5 1L7 7l-2 4 2 1v2l-2 1 2 4 2-.5 1.5 1L11 20h4l.5-2.5 1.5-1 2 .5 2-4-2-1z"],
];

export default function Layout() {
  const { me } = useAuth();
  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <aside className="side">
        <div className="brand"><span className="mark" aria-hidden="true">C</span> CampX AI</div>
        <nav aria-label="Main">
          {NAV.map(([to, label, d]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">Signed in as<br /><strong>{me?.user?.login_hint}</strong></div>
      </aside>
      <main id="main" className="main"><Outlet /></main>
    </div>
  );
}
