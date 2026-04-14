import { startTransition, useEffect, useState } from "react";
import SectionCard from "../components/SectionCard";
import DatasetAuditWorkflow from "../components/audit/DatasetAuditWorkflow";
import AggregateAuditWorkflow from "../components/audit/AggregateAuditWorkflow";
import AuditResultsPanel from "../components/audit/AuditResultsPanel";
import ReportPanel from "../components/audit/ReportPanel";

const EMPTY_DATASET_FORM = {
  org_name: "",
  model_name: "",
  domain: "",
  outcome_column: "",
  prediction_column: "",
  favorable_outcome: "1",
};

const EMPTY_AGGREGATE_FORM = {
  org_name: "",
  model_name: "",
  domain: "",
  attribute_name: "",
  groups: [
    { name: "Group A", total: "100", favorable: "60" },
    { name: "Group B", total: "100", favorable: "42" },
  ],
};

function buildBinningState(columns, protectedAttributes) {
  return protectedAttributes.reduce((accumulator, attribute) => {
    const column = columns.find((item) => item.name === attribute);
    if (column && /(int|float|double|number)/i.test(column.dtype)) {
      accumulator[attribute] = { method: "quartile" };
    }
    return accumulator;
  }, {});
}

function extractAuditPayload(job) {
  if (job?.results?.audit) {
    return job.results.audit;
  }
  return job?.results || null;
}

function extractReport(job) {
  return job?.results?.report || null;
}

export default function AuditStudioPage({ api }) {
  const [workspace, setWorkspace] = useState("dataset");
  const [resumeJobId, setResumeJobId] = useState("");
  const [datasetForm, setDatasetForm] = useState(EMPTY_DATASET_FORM);
  const [aggregateForm, setAggregateForm] = useState(EMPTY_AGGREGATE_FORM);
  const [selectedAttributes, setSelectedAttributes] = useState([]);
  const [referenceGroups, setReferenceGroups] = useState({});
  const [continuousBinning, setContinuousBinning] = useState({});
  const [uploadData, setUploadData] = useState(null);
  const [currentJob, setCurrentJob] = useState(null);
  const [auditResults, setAuditResults] = useState(null);
  const [report, setReport] = useState(null);
  const [samples, setSamples] = useState([]);
  const [modelFile, setModelFile] = useState(null);
  const [message, setMessage] = useState(null);
  const [loading, setLoading] = useState("");

  useEffect(() => {
    let active = true;
    api
      .getSamples()
      .then((response) => {
        if (active) {
          setSamples(response.datasets || []);
        }
      })
      .catch(() => {
        if (active) {
          setSamples([]);
        }
      });
    return () => {
      active = false;
    };
  }, [api]);

  const updateDatasetField = (field, value) => setDatasetForm((current) => ({ ...current, [field]: value }));
  const updateAggregateField = (field, value) => setAggregateForm((current) => ({ ...current, [field]: value }));

  async function loadJob(jobId, preferredWorkspace) {
    const job = await api.getJob(jobId);
    setCurrentJob(job);
    setUploadData(job.upload_summary?.columns ? { job_id: job.id, ...job.upload_summary } : null);
    setSelectedAttributes(job.config?.protected_attributes || []);
    setReferenceGroups(job.config?.reference_groups || {});
    setContinuousBinning(job.config?.continuous_binning || {});
    setDatasetForm((current) => ({
      ...current,
      org_name: job.config?.org_name || current.org_name,
      model_name: job.config?.model_name || current.model_name,
      domain: job.config?.domain || current.domain,
      outcome_column: job.config?.outcome_column || current.outcome_column,
      prediction_column: job.config?.prediction_column || "",
      favorable_outcome:
        job.config?.favorable_outcome !== undefined ? String(job.config.favorable_outcome) : current.favorable_outcome,
    }));
    setAuditResults(extractAuditPayload(job));
    setReport(extractReport(job));
    startTransition(() => setWorkspace(preferredWorkspace || (job.mode === "aggregate" ? "aggregate" : "dataset")));
    return job;
  }

  const pageState = {
    workspace,
    loading,
    message,
    resumeJobId,
    datasetForm,
    aggregateForm,
    selectedAttributes,
    referenceGroups,
    continuousBinning,
    uploadData,
    currentJob,
    auditResults,
    report,
    samples,
    modelFile,
    qualityReport: currentJob?.upload_summary?.quality_report || null,
  };

  const pageActions = {
    setWorkspace: (next) => startTransition(() => setWorkspace(next)),
    setResumeJobId,
    setDatasetForm,
    updateDatasetField,
    setAggregateForm,
    updateAggregateField,
    setSelectedAttributes,
    setReferenceGroups,
    setContinuousBinning,
    setUploadData,
    setCurrentJob,
    setAuditResults,
    setReport,
    setModelFile,
    setLoading,
    setMessage,
    buildBinningState,
    loadJob,
  };

  return (
    <div className="page-stack">
      <section className="hero-panel audit-hero">
        <div className="hero-copy">
          <p className="eyebrow">Audit studio</p>
          <h2>Run fairness audits from raw data to plain-language next steps.</h2>
          <p>
            Start with a dataset when you have row-level records. Use aggregate mode when you only have counts by
            group. The interface keeps the story understandable while preserving the evidence underneath.
          </p>
        </div>
        <div className="hero-metrics">
          <div className="hero-metric">
            <span className="hero-metric-value">{currentJob?.id ? currentJob.id.slice(0, 8) : "New"}</span>
            <span className="hero-metric-label">active audit workspace</span>
          </div>
          <div className="hero-metric">
            <span className="hero-metric-value">{currentJob?.status || "Not started"}</span>
            <span className="hero-metric-label">latest backend state</span>
          </div>
        </div>
      </section>

      {message ? <div className={`message-banner tone-${message.tone || "neutral"}`}>{message.text}</div> : null}

      <div className="workspace-switcher">
        <button
          className={`button-ghost tab-button${workspace === "dataset" ? " tab-button-active" : ""}`}
          onClick={() => pageActions.setWorkspace("dataset")}
          type="button"
        >
          Dataset workflow
        </button>
        <button
          className={`button-ghost tab-button${workspace === "aggregate" ? " tab-button-active" : ""}`}
          onClick={() => pageActions.setWorkspace("aggregate")}
          type="button"
        >
          Aggregate workflow
        </button>
      </div>

      <SectionCard title="Resume an existing job" subtitle="Paste a previous job ID to continue from where you left off.">
        <form
          className="inline-form"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!resumeJobId.trim()) {
              setMessage({ text: "Enter a job ID to reload an existing run.", tone: "negative" });
              return;
            }
            try {
              setLoading("resume");
              await loadJob(resumeJobId.trim());
              setMessage({ text: "Existing job loaded.", tone: "positive" });
            } catch (error) {
              setMessage({ text: error.detail || error.message, tone: "negative" });
            } finally {
              setLoading("");
            }
          }}
        >
          <input
            className="text-input"
            placeholder="Existing job ID"
            value={resumeJobId}
            onChange={(event) => setResumeJobId(event.target.value)}
          />
          <button className="button-primary" disabled={loading === "resume"} type="submit">
            {loading === "resume" ? "Loading..." : "Load job"}
          </button>
        </form>
      </SectionCard>

      {workspace === "dataset" ? (
        <DatasetAuditWorkflow api={api} state={pageState} actions={pageActions} />
      ) : (
        <AggregateAuditWorkflow api={api} state={pageState} actions={pageActions} />
      )}

      {auditResults ? <AuditResultsPanel auditResults={auditResults} /> : null}
      {report ? <ReportPanel api={api} currentJob={currentJob} report={report} setMessage={setMessage} /> : null}
    </div>
  );
}
