import SectionCard from "../SectionCard";
import StatusBadge from "../StatusBadge";
import { formatMetric, toTitleCase } from "../../utils/format";

function metricEntries(attributePayload) {
  return Object.entries(attributePayload?.metrics || {});
}

export default function AuditResultsPanel({ auditResults }) {
  return (
    <SectionCard
      title="4. Audit results"
      subtitle="The numbers stay visible, but the layout is organized around what needs attention and why."
    >
      <div className="results-grid">
        {Object.entries(auditResults.results || {}).map(([attribute, payload]) => (
          <article className="result-card" key={attribute}>
            <div className="result-card-head">
              <div>
                <h3>{attribute}</h3>
                <p>{payload.overall_passed ? "No threshold failures in this attribute." : `${payload.failed_count} metric checks need attention.`}</p>
              </div>
              <StatusBadge label={payload.overall_passed ? "pass" : "fail"} />
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Value</th>
                    <th>Threshold</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {metricEntries(payload).map(([metricName, metric]) => (
                    <tr key={metricName}>
                      <td>{toTitleCase(metricName)}</td>
                      <td>{metric.value === null ? "Not available" : formatMetric(metric.value)}</td>
                      <td>{metric.threshold === null ? "n/a" : formatMetric(metric.threshold)}</td>
                      <td>
                        <StatusBadge label={metric.passed === null ? "inconclusive" : metric.passed ? "pass" : "fail"} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Total</th>
                    <th>Favorable</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(payload.group_stats || {}).map(([group, stats]) => (
                    <tr key={group}>
                      <td>{group}</td>
                      <td>{stats.total}</td>
                      <td>{stats.favorable}</td>
                      <td>{formatMetric(stats.rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {auditResults.root_cause_analysis?.[attribute]?.length ? (
              <div className="hint-box">
                <strong>Likely drivers</strong>
                <ul className="detail-list">
                  {auditResults.root_cause_analysis[attribute].map((item, index) => (
                    <li key={`${item.feature}-${index}`}>
                      {item.feature}: {item.summary || `Influence score ${formatMetric(item.importance)}`}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </article>
        ))}
      </div>

      <div className="grid-two">
        <SectionCard title="Intersectional patterns" subtitle="Compound group checks help spot whether the worst impact appears only at intersections.">
          {Object.keys(auditResults.intersectional || {}).length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Intersection</th>
                    <th>Group</th>
                    <th>Rate</th>
                    <th>Relative to best</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(auditResults.intersectional).flatMap(([intersection, groups]) =>
                    Object.entries(groups).map(([groupName, details]) => (
                      <tr key={`${intersection}-${groupName}`}>
                        <td>{intersection}</td>
                        <td>{groupName}</td>
                        <td>{formatMetric(details.rate)}</td>
                        <td>{formatMetric(details.disparity_vs_best)}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted-copy">No intersectional warning crossed the current thresholds for this run.</p>
          )}
        </SectionCard>

        <SectionCard title="Possible proxy features" subtitle="These are non-protected fields that still move closely with a protected attribute.">
          {auditResults.proxy_features?.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Tracks with</th>
                    <th>Strength</th>
                    <th>Method</th>
                  </tr>
                </thead>
                <tbody>
                  {auditResults.proxy_features.map((item, index) => (
                    <tr key={`${item.feature}-${index}`}>
                      <td>{item.feature}</td>
                      <td>{item.correlated_with}</td>
                      <td>{formatMetric(item.correlation)}</td>
                      <td>{toTitleCase(item.method)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted-copy">No strong proxy-feature warning crossed the current threshold.</p>
          )}
        </SectionCard>
      </div>
    </SectionCard>
  );
}
