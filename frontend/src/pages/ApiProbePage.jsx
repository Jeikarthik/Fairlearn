import { useState } from "react";
import SectionCard from "../components/SectionCard";
import StatusBadge from "../components/StatusBadge";

const EMPTY_FORM = {
  org_name: "",
  system_name: "",
  domain: "",
  api_endpoint: "",
  method: "POST",
  input_schema_text: '{"name":"string","age":"integer","region":"string"}',
  protected_attribute: "gender",
  group_values_text: "Male,Female",
  decision_field: "",
  positive_values_text: "approve,allow,accept,positive,1",
  negative_values_text: "deny,reject,block,negative,0",
  num_test_pairs: "12",
  auth_type: "none",
  auth_key_name: "",
  auth_key_value: "",
  auth_username: "",
  auth_password: "",
  mock_outcomes_text: "",
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

export default function ApiProbePage({ api }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [setup, setSetup] = useState(null);
  const [results, setResults] = useState(null);
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
      api_endpoint: form.api_endpoint || null,
      method: form.method,
      input_schema: parseJson(form.input_schema_text, {}),
      protected_attribute: form.protected_attribute,
      group_values: parseCsv(form.group_values_text),
      decision_field: form.decision_field || null,
      positive_values: parseCsv(form.positive_values_text),
      negative_values: parseCsv(form.negative_values_text),
      num_test_pairs: Number(form.num_test_pairs || 12),
      auth: {
        type: form.auth_type,
        key_name: form.auth_key_name || null,
        key_value: form.auth_key_value || null,
        username: form.auth_username || null,
        password: form.auth_password || null,
      },
    };
  }

  function buildMockOutcomes() {
    return parseJson(form.mock_outcomes_text, []);
  }

  async function handleSetup(event) {
    event.preventDefault();
    try {
      setLoading("setup");
      const response = await api.configureApiProbe(buildSetupPayload());
      setSetup(response);
      setResults(null);
      setJobIdInput(response.job_id);
      setMessage({ text: "API probe configured. You can review the preview cases below, then run it.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  async function handleRun() {
    if (!setup?.job_id && !jobIdInput.trim()) {
      setMessage({ text: "Configure a probe or enter an existing probe job ID first.", tone: "negative" });
      return;
    }
    try {
      setLoading("run");
      const response = await api.runApiProbe(setup?.job_id || jobIdInput.trim(), buildMockOutcomes());
      setResults(response);
      setMessage({ text: "API probe run complete.", tone: "positive" });
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
      const response = await api.getApiProbe(jobIdInput.trim());
      setResults(response);
      setMessage({ text: "Saved API probe results loaded.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="page-stack">
      <SectionCard
        title="Mode 5: API probe"
        subtitle="Check whether a decision API changes its behavior when only a protected attribute changes."
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
              <span className="field-label">API endpoint (optional for live calls)</span>
              <input className="text-input" value={form.api_endpoint} onChange={(event) => update("api_endpoint", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Protected attribute</span>
              <input className="text-input" value={form.protected_attribute} onChange={(event) => update("protected_attribute", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Groups to compare</span>
              <input className="text-input" value={form.group_values_text} onChange={(event) => update("group_values_text", event.target.value)} />
            </label>
          </div>

          <label className="field-block">
            <span className="field-label">Input schema as JSON</span>
            <textarea className="textarea-input" rows="5" value={form.input_schema_text} onChange={(event) => update("input_schema_text", event.target.value)} />
          </label>

          <div className="form-grid">
            <label className="field-block">
              <span className="field-label">Decision field path (optional)</span>
              <input className="text-input" value={form.decision_field} onChange={(event) => update("decision_field", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Probe pairs</span>
              <input className="text-input" value={form.num_test_pairs} onChange={(event) => update("num_test_pairs", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Positive values</span>
              <input className="text-input" value={form.positive_values_text} onChange={(event) => update("positive_values_text", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Negative values</span>
              <input className="text-input" value={form.negative_values_text} onChange={(event) => update("negative_values_text", event.target.value)} />
            </label>
          </div>

          <details className="details-panel">
            <summary>Optional authentication</summary>
            <div className="form-grid top-gap">
              <label className="field-block">
                <span className="field-label">Auth type</span>
                <select className="select-input" value={form.auth_type} onChange={(event) => update("auth_type", event.target.value)}>
                  <option value="none">None</option>
                  <option value="bearer">Bearer token</option>
                  <option value="api_key_header">API key header</option>
                  <option value="api_key_query">API key query</option>
                  <option value="basic">Basic auth</option>
                </select>
              </label>
              <label className="field-block">
                <span className="field-label">Key name</span>
                <input className="text-input" value={form.auth_key_name} onChange={(event) => update("auth_key_name", event.target.value)} />
              </label>
              <label className="field-block">
                <span className="field-label">Key value</span>
                <input className="text-input" value={form.auth_key_value} onChange={(event) => update("auth_key_value", event.target.value)} />
              </label>
              <label className="field-block">
                <span className="field-label">Username</span>
                <input className="text-input" value={form.auth_username} onChange={(event) => update("auth_username", event.target.value)} />
              </label>
              <label className="field-block">
                <span className="field-label">Password</span>
                <input className="text-input" value={form.auth_password} onChange={(event) => update("auth_password", event.target.value)} />
              </label>
            </div>
          </details>

          <div className="action-line">
            <button className="button-primary" disabled={loading === "setup"} type="submit">
              {loading === "setup" ? "Saving..." : "Configure probe"}
            </button>
            <button className="button-secondary" disabled={loading === "run"} onClick={handleRun} type="button">
              {loading === "run" ? "Running..." : "Run probe"}
            </button>
          </div>
        </form>
      </SectionCard>

      <div className="grid-two">
        <SectionCard title="Preview cases" subtitle="These paired requests should stay aligned unless the API is behaving unevenly.">
          {setup?.preview_cases?.length ? (
            <div className="detail-stack">
              {setup.preview_cases.map((item) => (
                <article className="mini-panel" key={item.pair_id}>
                  <h3>{item.pair_id}</h3>
                  <pre className="code-block">{JSON.stringify(item.payloads, null, 2)}</pre>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted-copy">Configure the probe to preview the matched API payload pairs.</p>
          )}
        </SectionCard>

        <SectionCard title="Run options" subtitle="You can test with live API calls or provide mock outcomes as JSON for a dry run.">
          <label className="field-block">
            <span className="field-label">Existing probe job ID (optional)</span>
            <input className="text-input" value={jobIdInput} onChange={(event) => setJobIdInput(event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">Mock outcomes JSON array (optional)</span>
            <textarea className="textarea-input" rows="11" value={form.mock_outcomes_text} onChange={(event) => update("mock_outcomes_text", event.target.value)} placeholder='[{"pair_id":"probe-1","group":"Male","response":"approve"}]' />
          </label>
          <button className="button-ghost" disabled={loading === "load"} onClick={handleLoad} type="button">
            {loading === "load" ? "Loading..." : "Load saved results"}
          </button>
        </SectionCard>
      </div>

      {results ? (
        <SectionCard title="Probe findings" subtitle="The summary below is meant to be understandable even for teams who do not live in the API layer.">
          <div className="report-stack">
            <article className="insight-panel">
              <h3>{results.insight_headline}</h3>
              <p>{results.insight_summary}</p>
            </article>
            <article className="insight-panel">
              <h3>Recommended action</h3>
              <p>{results.recommended_action}</p>
              <div className="pill-row top-gap">
                <StatusBadge label={results.status} />
                <span>Discrepancy rate: {(results.discrepancy_rate * 100).toFixed(1)}%</span>
              </div>
            </article>
          </div>
          <div className="grid-two">
            <SectionCard title="Findings">
              <div className="detail-stack">
                {results.findings.map((item, index) => (
                  <article className="mini-panel" key={`${item.title}-${index}`}>
                    <div className="result-card-head">
                      <h3>{item.title}</h3>
                      <StatusBadge label={item.severity} />
                    </div>
                    <p>{item.summary}</p>
                  </article>
                ))}
              </div>
            </SectionCard>
            <SectionCard title="Pair outcomes">
              <div className="detail-stack">
                {results.pair_results.map((item) => (
                  <article className="mini-panel" key={item.pair_id}>
                    <div className="result-card-head">
                      <h3>{item.pair_id}</h3>
                      <StatusBadge label={item.changed_between_groups ? "warning" : "pass"} />
                    </div>
                    <pre className="code-block">{JSON.stringify(item.outcomes, null, 2)}</pre>
                  </article>
                ))}
              </div>
            </SectionCard>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
