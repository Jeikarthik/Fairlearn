import SectionCard from "../SectionCard";
import StatusBadge from "../StatusBadge";
import { downloadBlob, formatMetric } from "../../utils/format";

export default function ReportPanel({ api, currentJob, report, setMessage }) {
  async function handleDownloadPdf() {
    if (!currentJob?.id) {
      return;
    }
    try {
      const blob = await api.downloadReportPdf(currentJob.id);
      downloadBlob(blob, `FairLens_Audit_${currentJob.id}.pdf`);
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    }
  }

  async function handleMitigationDownload(method) {
    if (!currentJob?.id) {
      return;
    }
    try {
      const blob = await api.downloadMitigation(currentJob.id, method);
      downloadBlob(blob, `FairLens_${method}_${currentJob.id}.csv`);
    } catch (error) {
      setMessage({ text: error.detail || error.message, tone: "negative" });
    }
  }

  return (
    <SectionCard
      title="5. Plain-language report"
      subtitle="This report is written to help someone decide what to do next, not just what number changed."
      actions={
        <div className="section-actions">
          <button className="button-secondary" onClick={handleDownloadPdf} type="button">
            Download PDF
          </button>
          <button className="button-ghost" onClick={() => handleMitigationDownload("reweight")} type="button">
            Download reweight CSV
          </button>
          <button className="button-ghost" onClick={() => handleMitigationDownload("resample")} type="button">
            Download resample CSV
          </button>
        </div>
      }
    >
      <div className="report-stack">
        <article className="insight-panel">
          <h3>Executive summary</h3>
          <p>{report.executive_summary}</p>
        </article>
        <article className="insight-panel">
          <h3>Priority action</h3>
          <p>{report.priority_action}</p>
        </article>
      </div>

      <div className="grid-two">
        <SectionCard title="Attribute breakdowns">
          <div className="detail-stack">
            {(report.attribute_breakdowns || []).map((item) => (
              <article className="mini-panel" key={item.attribute}>
                <h3>{item.attribute}</h3>
                <p>{item.paragraph}</p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Wider findings">
          <div className="detail-stack">
            <article className="mini-panel">
              <h3>Intersectional findings</h3>
              <p>{report.intersectional_findings}</p>
            </article>
            <article className="mini-panel">
              <h3>Proxy-feature warning</h3>
              <p>{report.proxy_warnings}</p>
            </article>
          </div>
        </SectionCard>
      </div>

      <SectionCard title="Mitigation options" subtitle="These are framed as operational choices so teams can discuss trade-offs without diving into implementation jargon first.">
        <div className="detail-stack">
          {(report.mitigation_cards || []).map((card, index) => (
            <article className="mitigation-card" key={`${card.title}-${index}`}>
              <div className="result-card-head">
                <div>
                  <h3>{card.title}</h3>
                  <p>{card.action}</p>
                </div>
                <StatusBadge label={card.severity} />
              </div>
              {card.tradeoff ? <p className="muted-copy">{card.tradeoff}</p> : null}
              {card.tradeoff_options?.length ? (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Option</th>
                        <th>Projected accuracy</th>
                        <th>Fairness ratio</th>
                        <th>Approval-rate gap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {card.tradeoff_options.map((option) => (
                        <tr key={option.label}>
                          <td>
                            <strong>{option.label}</strong>
                            <div className="table-note">{option.summary}</div>
                          </td>
                          <td>{option.projected_accuracy === null ? "n/a" : formatMetric(option.projected_accuracy)}</td>
                          <td>{option.projected_disparate_impact === null ? "n/a" : formatMetric(option.projected_disparate_impact)}</td>
                          <td>
                            {option.projected_demographic_parity_gap === null
                              ? "n/a"
                              : formatMetric(option.projected_demographic_parity_gap)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </SectionCard>
    </SectionCard>
  );
}
