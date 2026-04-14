import { NavLink } from "react-router-dom";
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
