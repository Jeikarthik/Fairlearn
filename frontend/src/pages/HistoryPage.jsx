import { useDeferredValue, useEffect, useState } from "react";
import SectionCard from "../components/SectionCard";
import StatusBadge from "../components/StatusBadge";

export default function HistoryPage({ api }) {
  const [audits, setAudits] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedOld, setSelectedOld] = useState("");
  const [selectedNew, setSelectedNew] = useState("");
  const [comparison, setComparison] = useState(null);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState("");
  const deferredSearch = useDeferredValue(search);

  async function loadHistory() {
    try {
      setLoading("history");
      const response = await api.listHistory();
      setAudits(response.audits || []);
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  const filtered = audits.filter((item) => {
    const text = `${item.id} ${item.mode} ${item.filename || ""}`.toLowerCase();
    return text.includes(deferredSearch.toLowerCase());
  });

  async function handleCompare() {
    if (!selectedOld || !selectedNew) {
      setMessage({ text: "Choose two runs to compare.", tone: "negative" });
      return;
    }
    try {
      setLoading("compare");
      const response = await api.compareHistory(selectedOld, selectedNew);
      setComparison(response);
      setMessage({ text: "Comparison ready.", tone: "positive" });
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      setLoading("");
    }
  }

  return (
    <div className="page-stack">
      <SectionCard title="Audit history" subtitle="Track earlier runs, reload IDs, and compare whether fairness moved in the right direction.">
        {message ? <div className={`message-banner tone-${message.tone || "neutral"}`}>{message.text}</div> : null}
        <div className="action-line">
          <input className="text-input" placeholder="Search by job ID, mode, or filename" value={search} onChange={(event) => setSearch(event.target.value)} />
          <button className="button-secondary" disabled={loading === "history"} onClick={loadHistory} type="button">
            {loading === "history" ? "Refreshing..." : "Refresh history"}
          </button>
        </div>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Filename</th>
                <th>Overall result</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id}>
                  <td className="mono-text">{item.id}</td>
                  <td>{item.mode}</td>
                  <td>
                    <StatusBadge label={item.status} />
                  </td>
                  <td>{item.filename || "n/a"}</td>
                  <td>{item.overall_passed === null ? "Not run yet" : item.overall_passed ? "Passed" : "Needs review"}</td>
                  <td>{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard title="Compare two runs" subtitle="Use this to understand whether the latest change improved or worsened fairness.">
        <div className="form-grid">
          <label className="field-block">
            <span className="field-label">Earlier run</span>
            <select className="select-input" value={selectedOld} onChange={(event) => setSelectedOld(event.target.value)}>
              <option value="">Choose a run</option>
              {audits.map((item) => (
                <option key={`old-${item.id}`} value={item.id}>
                  {item.id} · {item.mode}
                </option>
              ))}
            </select>
          </label>
          <label className="field-block">
            <span className="field-label">Later run</span>
            <select className="select-input" value={selectedNew} onChange={(event) => setSelectedNew(event.target.value)}>
              <option value="">Choose a run</option>
              {audits.map((item) => (
                <option key={`new-${item.id}`} value={item.id}>
                  {item.id} · {item.mode}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button className="button-primary" disabled={loading === "compare"} onClick={handleCompare} type="button">
          {loading === "compare" ? "Comparing..." : "Compare runs"}
        </button>

        {comparison ? (
          <div className="table-wrap top-gap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Attribute</th>
                  <th>Metric</th>
                  <th>Old</th>
                  <th>New</th>
                  <th>Delta</th>
                  <th>Direction</th>
                </tr>
              </thead>
              <tbody>
                {comparison.comparisons.map((item, index) => (
                  <tr key={`${item.attribute}-${item.metric}-${index}`}>
                    <td>{item.attribute}</td>
                    <td>{item.metric}</td>
                    <td>{item.old_value}</td>
                    <td>{item.new_value}</td>
                    <td>{item.delta}</td>
                    <td>
                      <StatusBadge label={item.direction} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}
