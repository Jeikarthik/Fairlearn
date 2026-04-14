import { Link } from "react-router-dom";
import SectionCard from "../components/SectionCard";

const quickActions = [
  {
    title: "Run a fairness audit",
    description: "Upload a dataset or enter aggregate counts, then turn the results into a plain-language report.",
    to: "/audit",
  },
  {
    title: "Probe a live API",
    description: "Check whether a decision API behaves differently when only a protected attribute changes.",
    to: "/probe",
  },
  {
    title: "Stress-test language prompts",
    description: "Compare equivalent prompts across demographic variants and surface plain-language findings.",
    to: "/language-probe",
  },
  {
    title: "Watch fairness drift over time",
    description: "Connect a webhook once and keep track of whether recent decisions are drifting out of bounds.",
    to: "/monitor",
  },
];

export default function DashboardPage({ api, health }) {
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Fairness you can explain</p>
          <h2>One place to audit, probe, and monitor responsible decision systems.</h2>
          <p>
            FairLens turns technical setup into understandable next steps so operations, risk, and leadership teams can
            act on bias findings without reading raw metrics all day.
          </p>
          <div className="hero-actions">
            <Link className="button-primary" to="/audit">
              Start an audit
            </Link>
            <Link className="button-secondary" to="/history">
              Review past runs
            </Link>
          </div>
        </div>
        <div className="hero-metrics">
          <div className="hero-metric">
            <span className="hero-metric-value">7</span>
            <span className="hero-metric-label">connected workflows</span>
          </div>
          <div className="hero-metric">
            <span className="hero-metric-value">{health.status === "online" ? "Live" : "Waiting"}</span>
            <span className="hero-metric-label">backend state</span>
          </div>
          <div className="hero-metric">
            <span className="hero-metric-value">Plain language</span>
            <span className="hero-metric-label">default insight style</span>
          </div>
        </div>
      </section>

      <div className="grid-two">
        <SectionCard
          title="What teams can do here"
          subtitle="Pick the workflow that matches your current job. The interface keeps the wording practical for non-technical users."
        >
          <div className="action-grid">
            {quickActions.map((item) => (
              <Link key={item.to} className="action-card" to={item.to}>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </Link>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="Connected backend"
          subtitle="This frontend is wired to the FastAPI service already running behind FairLens."
        >
          <ul className="detail-list">
            <li>Dataset upload and aggregate-mode audits</li>
            <li>Mode 5 API probing, Mode 6 language probing, and Mode 7 live monitoring</li>
            <li>Report generation, PDF export, mitigation downloads, and audit history comparison</li>
            <li>Optional model upload for root-cause hints when a compatible model artifact is available</li>
          </ul>
        </SectionCard>
      </div>
    </div>
  );
}
