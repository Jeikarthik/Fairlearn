import SectionCard from "../SectionCard";

export default function AggregateAuditWorkflow({ api, state, actions }) {
  const { aggregateForm, currentJob, auditResults, loading } = state;

  function updateGroup(index, field, value) {
    actions.setAggregateForm((current) => ({
      ...current,
      groups: current.groups.map((group, groupIndex) => (groupIndex === index ? { ...group, [field]: value } : group)),
    }));
  }

  function addGroup() {
    actions.setAggregateForm((current) => ({
      ...current,
      groups: [...current.groups, { name: "", total: "0", favorable: "0" }],
    }));
  }

  function removeGroup(index) {
    actions.setAggregateForm((current) => ({
      ...current,
      groups: current.groups.filter((_, groupIndex) => groupIndex !== index),
    }));
  }

  async function handleAggregateAudit(event) {
    event.preventDefault();
    try {
      actions.setLoading("aggregate");
      const created = await api.aggregateInput({
        ...aggregateForm,
        groups: aggregateForm.groups.map((group) => ({
          name: group.name,
          total: Number(group.total),
          favorable: Number(group.favorable),
        })),
      });
      await api.runAudit(created.job_id);
      await actions.loadJob(created.job_id, "aggregate");
      actions.setMessage({ text: "Aggregate audit completed. You can review results immediately or generate a report.", tone: "positive" });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleGenerateReport() {
    if (!currentJob?.id) {
      return;
    }
    try {
      actions.setLoading("report");
      const result = await api.generateReport(currentJob.id);
      actions.setReport(result);
      await actions.loadJob(currentJob.id, "aggregate");
      actions.setMessage({ text: "Plain-language report generated for the aggregate audit.", tone: "positive" });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  return (
    <SectionCard
      title="Aggregate fairness audit"
      subtitle="Use this when you only have counts per group and not row-level records."
    >
      <form className="stack-form" onSubmit={handleAggregateAudit}>
        <div className="form-grid">
          <label className="field-block">
            <span className="field-label">Organization</span>
            <input className="text-input" value={aggregateForm.org_name} onChange={(event) => actions.updateAggregateField("org_name", event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">System or model name</span>
            <input className="text-input" value={aggregateForm.model_name} onChange={(event) => actions.updateAggregateField("model_name", event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">Domain</span>
            <input className="text-input" value={aggregateForm.domain} onChange={(event) => actions.updateAggregateField("domain", event.target.value)} />
          </label>
          <label className="field-block">
            <span className="field-label">Attribute being compared</span>
            <input className="text-input" placeholder="gender, region, caste_category..." value={aggregateForm.attribute_name} onChange={(event) => actions.updateAggregateField("attribute_name", event.target.value)} />
          </label>
        </div>

        <div className="stack-form">
          {aggregateForm.groups.map((group, index) => (
            <div className="group-row" key={`${group.name}-${index}`}>
              <input className="text-input" placeholder="Group name" value={group.name} onChange={(event) => updateGroup(index, "name", event.target.value)} />
              <input className="text-input" placeholder="Total people" value={group.total} onChange={(event) => updateGroup(index, "total", event.target.value)} />
              <input className="text-input" placeholder="Favorable outcomes" value={group.favorable} onChange={(event) => updateGroup(index, "favorable", event.target.value)} />
              <button className="button-ghost" onClick={() => removeGroup(index)} type="button">
                Remove
              </button>
            </div>
          ))}
        </div>

        <div className="action-line">
          <button className="button-secondary" onClick={addGroup} type="button">
            Add group
          </button>
          <button className="button-primary" disabled={loading === "aggregate"} type="submit">
            {loading === "aggregate" ? "Running..." : "Run aggregate audit"}
          </button>
          <button className="button-ghost" disabled={!auditResults || loading === "report"} onClick={handleGenerateReport} type="button">
            {loading === "report" ? "Generating..." : "Generate report"}
          </button>
        </div>
      </form>
    </SectionCard>
  );
}
