import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "./StatusBadge";

const navigation = [
  { to: "/", label: "Overview" },
  { to: "/audit", label: "Audit Studio" },
  { to: "/probe", label: "API Probe" },
  { to: "/language-probe", label: "Language Probe" },
  { to: "/monitor", label: "Live Monitor" },
  { to: "/history", label: "History" },
];

export default function Layout({ apiBase, onApiBaseChange, health, children }) {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="brand-block">
          <div className="brand-mark">FL</div>
          <div>
            <p className="eyebrow">Accessible fairness operations</p>
            <h1>FairLens</h1>
          </div>
        </div>
        <p className="sidebar-copy">
          Technical teams connect the system once. Everyone else gets clear, plain-language insight.
        </p>

        <nav className="nav-stack">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? " nav-link-active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* User pill — shown when authenticated */}
        {isAuthenticated && user && (
          <div className="user-pill">
            <div className="user-pill-avatar">
              {(user.full_name || user.email || "U").charAt(0).toUpperCase()}
            </div>
            <div className="user-pill-info">
              <span className="user-pill-name">{user.full_name || user.email}</span>
              <span className="user-pill-role">{user.role} · {user.org_name || "Org"}</span>
            </div>
            <button className="user-pill-logout" onClick={logout} title="Sign out" type="button">
              ↗
            </button>
          </div>
        )}

        <div className="sidebar-panel">
          <label className="field-label" htmlFor="api-base">
            Backend API
          </label>
          <input
            id="api-base"
            className="text-input"
            value={apiBase}
            onChange={(event) => onApiBaseChange(event.target.value)}
          />
          <div className="sidebar-status">
            <StatusBadge label={health.status} tone={health.status} />
            <span>{health.detail}</span>
          </div>
        </div>
      </aside>

      <main className="app-main">
        <div className="ambient ambient-one" />
        <div className="ambient ambient-two" />
        {children}
      </main>
    </div>
  );
}
