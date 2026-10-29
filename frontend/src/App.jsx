import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import Login from "./pages/Login.jsx";
import Overview from "./pages/Overview.jsx";
import Profile from "./pages/Profile.jsx";
import Timetable from "./pages/Timetable.jsx";
import Attendance from "./pages/Attendance.jsx";
import Subjects from "./pages/Subjects.jsx";
import Settings from "./pages/Settings.jsx";

export default function App() {
  const { status } = useAuth();
  if (status === "loading") return <div className="boot" role="status">Loading CampX AI…</div>;
  if (status === "anon") {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/timetable" element={<Timetable />} />
        <Route path="/attendance" element={<Attendance />} />
        <Route path="/subjects" element={<Subjects />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
