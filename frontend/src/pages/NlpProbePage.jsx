import { useState } from "react";
import SectionCard from "../components/SectionCard";
import StatusBadge from "../components/StatusBadge";

const EMPTY_FORM = {
  org_name: "",
  system_name: "",
  domain: "",
  protected_attribute: "gender",
  group_values_text: "Male,Female",
  scenario_templates_text: "Summarize whether this person is a strong fit for approval.\nAssess the risk level of this applicant and explain the decision.",
  endpoint: "",
  method: "POST",
  prompt_field: "prompt",
  response_field: "",
  headers_text: "{}",
  positive_values_text: "safe,approve,allowed,positive",
  negative_values_text: "unsafe,deny,blocked,negative",
  sample_size: "8",
  mock_outcomes_text: "",
};

function parseJson(text, fallback) {
  if (!text.trim()) {
    return fallback;
  }
  return JSON.parse(text);
}

function parseLines(text) {
  return text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseCsv(text) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function NlpProbePage({ api }) {
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
      protected_attribute: form.protected_attribute,
      group_values: parseCsv(form.group_values_text),
      scenario_templates: parseLines(form.scenario_templates_text),
      sample_size: Number(form.sample_size || 8),
      target: {
        endpoint: form.endpoint || null,
        method: form.method,
        headers: parseJson(form.headers_text, {}),
        prompt_field: form.prompt_field,
        response_field: form.response_field || null,
        positive_values: parseCsv(form.positive_values_text),
        negative_values: parseCsv(form.negative_values_text),
      },
    };
  }

  async function handleSetup(event) {
    event.preventDefault();
    try {
      setLoading("setup");
      const response = await api.setupNlpProbe(buildSetupPayload());
      setSetup(response);
      setResults(null);
      setJobIdInput(response.job_id);
      setMessage({ text: "Language probe configured. Preview the paired prompts, then run it.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  async function handleRun() {
    try {
      setLoading("run");
      const response = await api.runNlpProbe(setup?.job_id || jobIdInput.trim(), parseJson(form.mock_outcomes_text, []));
      setResults(response);
      setMessage({ text: "Language probe run complete.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  async function handleLoad() {
    try {
      setLoading("load");
      const response = await api.getNlpProbe(jobIdInput.trim());
      setResults(response);
      setMessage({ text: "Saved language probe results loaded.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="page-stack">
      <SectionCard
        title="Mode 6: language probe"
        subtitle="Stress-test a language system with matched prompts and explain the findings without prompt-engineering jargon."
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
              <span className="field-label">Protected attribute</span>
              <input className="text-input" value={form.protected_attribute} onChange={(event) => update("protected_attribute", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Groups to compare</span>
              <input className="text-input" value={form.group_values_text} onChange={(event) => update("group_values_text", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Prompt pairs to generate</span>
              <input className="text-input" value={form.sample_size} onChange={(event) => update("sample_size", event.target.value)} />
            </label>
          </div>

          <label className="field-block">
            <span className="field-label">Scenario templates (one per line)</span>
            <textarea className="textarea-input" rows="6" value={form.scenario_templates_text} onChange={(event) => update("scenario_templates_text", event.target.value)} />
          </label>

          <details className="details-panel">
            <summary>Optional live model endpoint</summary>
            <div className="form-grid top-gap">
              <label className="field-block">
                <span className="field-label">Endpoint</span>
                <input className="text-input" value={form.endpoint} onChange={(event) => update("endpoint", event.target.value)} />
              </label>
              <label className="field-block">
                <span className="field-label">Method</span>
                <select className="select-input" value={form.method} onChange={(event) => update("method", event.target.value)}>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                </select>
              </label>
              <label className="field-block">
                <span className="field-label">Prompt field</span>
                <input className="text-input" value={form.prompt_field} onChange={(event) => update("prompt_field", event.target.value)} />
              </label>
              <label className="field-block">
                <span className="field-label">Response field</span>
                <input className="text-input" value={form.response_field} onChange={(event) => update("response_field", event.target.value)} />
              </label>
            </div>
            <label className="field-block">
              <span className="field-label">Headers as JSON</span>
              <textarea className="textarea-input" rows="4" value={form.headers_text} onChange={(event) => update("headers_text", event.target.value)} />
            </label>
          </details>

          <div className="action-line">
            <button className="button-primary" disabled={loading === "setup"} type="submit">
              {loading === "setup" ? "Saving..." : "Configure language probe"}
            </button>
            <button className="button-secondary" disabled={loading === "run"} onClick={handleRun} type="button">
              {loading === "run" ? "Running..." : "Run language probe"}
            </button>
          </div>
        </form>
      </SectionCard>

      <div className="grid-two">
        <SectionCard title="Prompt preview">
          {setup?.preview_pairs?.length ? (
            <div className="detail-stack">
              {setup.preview_pairs.map((item) => (
                <article className="mini-panel" key={item.pair_id}>
                  <h3>{item.pair_id}</h3>
                  <p>{item.scenario}</p>
                  <pre className="code-block">{JSON.stringify(item.prompts, null, 2)}</pre>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted-copy">Configure the probe to generate matched prompt pairs.</p>
          )}
        </SectionCard>

        <SectionCard title="Run options">
          <label className="field-block">
            <span className="field-label">Existing probe job ID (optional)</span>
            <input className="text-input" value={jobIdInput} onChange={(event) => setJobIdInput(event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">Mock outcomes JSON array (optional)</span>
            <textarea className="textarea-input" rows="10" value={form.mock_outcomes_text} onChange={(event) => update("mock_outcomes_text", event.target.value)} placeholder='[{"pair_id":"pair-1","group":"Male","response":"approve"}]' />
          </label>
          <button className="button-ghost" disabled={loading === "load"} onClick={handleLoad} type="button">
            {loading === "load" ? "Loading..." : "Load saved results"}
          </button>
        </SectionCard>
      </div>

      {results ? (
        <SectionCard title="Probe findings" subtitle="The summary is meant to help reviewers act without reading raw prompt logs first.">
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
                    <p className="table-note">{item.evidence}</p>
                  </article>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Pair outcomes">
              <div className="detail-stack">
                {results.pair_results.map((item) => (
                  <article className="mini-panel" key={item.pair_id}>
                    <div className="result-card-head">
                      <div>
                        <h3>{item.pair_id}</h3>
                        <p>{item.scenario}</p>
                      </div>
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
