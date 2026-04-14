import { useState } from "react";
import SectionCard from "../components/SectionCard";
import StatusBadge from "../components/StatusBadge";

const EMPTY_FORM = {
  org_name: "",
  system_name: "",
  domain: "",
  protected_attributes_text: "gender,region",
  prediction_field: "prediction",
  outcome_field: "",
  favorable_outcome: "1",
  demographic_parity_gap: "0.10",
  disparate_impact_ratio: "0.80",
  alert_window_size: "50",
  records_text:
    '[\n  {"gender":"Female","region":"Rural","prediction":0},\n  {"gender":"Male","region":"Urban","prediction":1}\n]',
};

function parseJson(text, fallback) {
  if (!text.trim()) {
    return fallback;
  }
  return JSON.parse(text);
}

function parseCsv(text) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function MonitoringPage({ api }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [setup, setSetup] = useState(null);
  const [status, setStatus] = useState(null);
  const [jobIdInput, setJobIdInput] = useState("");
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState("");

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function buildSetupPayload() {
    return {
      org_name: form.org_name,
      system_name: form.system_name,
      domain: form.domain,
      protected_attributes: parseCsv(form.protected_attributes_text),
      prediction_field: form.prediction_field,
      outcome_field: form.outcome_field || null,
      favorable_outcome: form.favorable_outcome === "" ? 1 : Number.isNaN(Number(form.favorable_outcome)) ? form.favorable_outcome : Number(form.favorable_outcome),
      thresholds: {
        demographic_parity_gap: Number(form.demographic_parity_gap),
        disparate_impact_ratio: Number(form.disparate_impact_ratio),
        alert_window_size: Number(form.alert_window_size),
      },
    };
  }

  async function handleSetup(event) {
    event.preventDefault();
    try {
      setLoading("setup");
      const response = await api.setupMonitoring(buildSetupPayload());
      setSetup(response);
      setJobIdInput(response.job_id);
      setStatus(null);
      setMessage({ text: "Monitoring setup saved. Connect the webhook or simulate a batch below.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  async function handleSendRecords() {
    if (!setup?.job_id && !jobIdInput.trim()) {
      setMessage({ text: "Configure monitoring or enter an existing monitoring job ID first.", tone: "negative" });
      return;
    }
    try {
      setLoading("ingest");
      const response = await api.sendMonitoringRecords(setup?.job_id || jobIdInput.trim(), parseJson(form.records_text, []));
      setStatus(response);
      setMessage({ text: "Monitoring window updated with the new records.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  async function handleLoad() {
    if (!jobIdInput.trim()) {
      return;
    }
    try {
      setLoading("load");
      const response = await api.getMonitoring(jobIdInput.trim());
      setStatus(response);
      setMessage({ text: "Monitoring status loaded.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="page-stack">
      <SectionCard
        title="Mode 7: live monitor"
        subtitle="Set up a webhook once, then translate fairness drift into understandable operational alerts."
      >
        {message ? <div className={`message-banner tone-${message.tone || "neutral"}`}>{message.text}</div> : null}
        <form className="stack-form" onSubmit={handleSetup}>
          <div className="form-grid">
            <label className="field-block">
              <span className="field-label">Organization</span>
              <input className="text-input" value={form.org_name} onChange={(event) => update("org_name", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">System name</span>
              <input className="text-input" value={form.system_name} onChange={(event) => update("system_name", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Domain</span>
              <input className="text-input" value={form.domain} onChange={(event) => update("domain", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Protected attributes</span>
              <input className="text-input" value={form.protected_attributes_text} onChange={(event) => update("protected_attributes_text", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Prediction field</span>
              <input className="text-input" value={form.prediction_field} onChange={(event) => update("prediction_field", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Favorable outcome</span>
              <input className="text-input" value={form.favorable_outcome} onChange={(event) => update("favorable_outcome", event.target.value)} />
            </label>
          </div>

          <div className="form-grid">
            <label className="field-block">
              <span className="field-label">Approval-rate gap alert</span>
              <input className="text-input" value={form.demographic_parity_gap} onChange={(event) => update("demographic_parity_gap", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Fairness ratio floor</span>
              <input className="text-input" value={form.disparate_impact_ratio} onChange={(event) => update("disparate_impact_ratio", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Monitoring window size</span>
              <input className="text-input" value={form.alert_window_size} onChange={(event) => update("alert_window_size", event.target.value)} />
            </label>
          </div>

          <div className="action-line">
            <button className="button-primary" disabled={loading === "setup"} type="submit">
              {loading === "setup" ? "Saving..." : "Configure monitor"}
            </button>
            <button className="button-secondary" disabled={loading === "ingest"} onClick={handleSendRecords} type="button">
              {loading === "ingest" ? "Sending..." : "Send sample records"}
            </button>
          </div>
        </form>
      </SectionCard>

      <div className="grid-two">
        <SectionCard title="Webhook details">
          {setup ? (
            <div className="detail-stack">
              <article className="mini-panel">
                <h3>Setup note</h3>
                <p>{setup.operator_note}</p>
              </article>
              <article className="mini-panel">
                <h3>Webhook path</h3>
                <pre className="code-block">{setup.webhook_path}</pre>
              </article>
            </div>
          ) : (
            <p className="muted-copy">Configure monitoring to generate the webhook path for your prediction system.</p>
          )}
        </SectionCard>

        <SectionCard title="Simulate or reload status">
          <label className="field-block">
            <span className="field-label">Monitoring job ID</span>
            <input className="text-input" value={jobIdInput} onChange={(event) => setJobIdInput(event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">Records JSON array</span>
            <textarea className="textarea-input" rows="10" value={form.records_text} onChange={(event) => update("records_text", event.target.value)} />
          </label>
          <button className="button-ghost" disabled={loading === "load"} onClick={handleLoad} type="button">
            {loading === "load" ? "Loading..." : "Load current status"}
          </button>
        </SectionCard>
      </div>

      {status ? (
        <SectionCard title="Monitoring summary" subtitle="This view translates fairness drift into updates an operations team can actually use.">
          <div className="report-stack">
            <article className="insight-panel">
              <h3>{status.insight_headline}</h3>
              <p>{status.insight_summary}</p>
            </article>
            <article className="insight-panel">
              <h3>Recommended action</h3>
              <p>{status.recommended_action}</p>
              <div className="pill-row top-gap">
                <StatusBadge label={status.status} />
                <span>{status.records_seen} records seen</span>
              </div>
            </article>
          </div>

          <div className="grid-two">
            <SectionCard title="Alerts">
              {status.alerts.length ? (
                <div className="detail-stack">
                  {status.alerts.map((alert, index) => (
                    <article className="mini-panel" key={`${alert.title}-${index}`}>
                      <div className="result-card-head">
                        <h3>{alert.title}</h3>
                        <StatusBadge label={alert.severity} />
                      </div>
                      <p>{alert.summary}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted-copy">No alerts are active in the latest monitoring window.</p>
              )}
            </SectionCard>
            <SectionCard title="Latest snapshot">
              <pre className="code-block">{JSON.stringify(status.latest_snapshot, null, 2)}</pre>
            </SectionCard>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
