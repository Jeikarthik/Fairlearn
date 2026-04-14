import SectionCard from "../SectionCard";
import StatusBadge from "../StatusBadge";
import { downloadBlob, parsePrimitive } from "../../utils/format";

function suggestionText(suggestion) {
  return `${suggestion.column}: ${suggestion.reason}`;
}

export default function DatasetAuditWorkflow({ api, state, actions }) {
  const {
    loading,
    datasetForm,
    selectedAttributes,
    referenceGroups,
    continuousBinning,
    uploadData,
    currentJob,
    samples,
    qualityReport,
  } = state;

  const columns = uploadData?.columns || [];
  const datasetReadyForConfigure = Boolean(uploadData?.job_id);
  const datasetReadyForAudit = Boolean(currentJob?.config && currentJob.id);
  const selectedColumnOptions = new Set(selectedAttributes);

  function toggleAttribute(attribute) {
    actions.setSelectedAttributes((current) => {
      if (current.includes(attribute)) {
        const next = current.filter((item) => item !== attribute);
        actions.setContinuousBinning((binning) => {
          const updated = { ...binning };
          delete updated[attribute];
          return updated;
        });
        actions.setReferenceGroups((groups) => {
          const updated = { ...groups };
          delete updated[attribute];
          return updated;
        });
        return next;
      }
      const next = [...current, attribute];
      const column = columns.find((item) => item.name === attribute);
      if (column && /(int|float|double|number)/i.test(column.dtype)) {
        actions.setContinuousBinning((currentBinning) => ({
          ...currentBinning,
          [attribute]: { method: "quartile" },
        }));
      }
      return next;
    });
  }

  async function handleDatasetUpload(event) {
    event.preventDefault();
    const fileInput = event.currentTarget.elements.namedItem("dataset-file");
    const file = fileInput?.files?.[0];
    if (!file) {
      actions.setMessage({ text: "Choose a CSV or Excel file to start the audit.", tone: "negative" });
      return;
    }
    try {
      actions.setLoading("upload");
      const response = await api.uploadDataset(file, datasetForm.prediction_column ? "prediction" : "dataset");
      actions.setUploadData(response);
      actions.setCurrentJob({
        id: response.job_id,
        mode: response.mode,
        status: "uploaded",
        filename: file.name,
        upload_summary: response,
        config: null,
        results: null,
      });
      const suggested = (response.suggested_protected_attributes || []).map((item) => item.column);
      actions.setSelectedAttributes(suggested);
      actions.setReferenceGroups({});
      actions.setContinuousBinning(actions.buildBinningState(response.columns || [], suggested));
      actions.updateDatasetField("outcome_column", response.columns?.[0]?.name || "");
      actions.setReport(null);
      actions.setAuditResults(null);
      actions.setMessage({
        text: "Dataset uploaded. Pick the outcome and protected attributes, then save the setup.",
        tone: "positive",
      });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleConfigureDataset(event) {
    event.preventDefault();
    if (!currentJob?.id) {
      actions.setMessage({ text: "Upload a dataset first.", tone: "negative" });
      return;
    }
    try {
      actions.setLoading("configure");
      const payload = {
        job_id: currentJob.id,
        org_name: datasetForm.org_name,
        model_name: datasetForm.model_name,
        domain: datasetForm.domain,
        outcome_column: datasetForm.outcome_column,
        prediction_column: datasetForm.prediction_column || null,
        favorable_outcome: parsePrimitive(datasetForm.favorable_outcome),
        protected_attributes: selectedAttributes,
        continuous_binning: continuousBinning,
        reference_groups: referenceGroups,
        mode: datasetForm.prediction_column ? "prediction" : "dataset",
      };
      await api.configure(payload);
      await actions.loadJob(currentJob.id, "dataset");
      actions.setMessage({
        text: "Audit setup saved. You can optionally attach a model file, run checks, and then audit.",
        tone: "positive",
      });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleModelUpload() {
    if (!currentJob?.id || !state.modelFile) {
      actions.setMessage({ text: "Choose a model file before uploading it.", tone: "negative" });
      return;
    }
    try {
      actions.setLoading("model");
      await api.uploadModel(currentJob.id, state.modelFile);
      await actions.loadJob(currentJob.id, "dataset");
      actions.setMessage({
        text: "Model artifact attached. Root-cause hints will use it where supported.",
        tone: "positive",
      });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleQualityCheck() {
    if (!currentJob?.id) {
      return;
    }
    try {
      actions.setLoading("quality");
      await api.qualityCheck(currentJob.id);
      await actions.loadJob(currentJob.id, "dataset");
      actions.setMessage({ text: "Pre-audit checks are ready below.", tone: "positive" });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleRunAudit() {
    if (!currentJob?.id) {
      return;
    }
    try {
      actions.setLoading("audit");
      await api.runAudit(currentJob.id);
      await actions.loadJob(currentJob.id, "dataset");
      actions.setMessage({
        text: "Audit completed. Review the fairness summary and plain-language guidance below.",
        tone: "positive",
      });
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
      await actions.loadJob(currentJob.id, "dataset");
      actions.setMessage({
        text: "Report generated. You can download the PDF or use the mitigation downloads now.",
        tone: "positive",
      });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    } finally {
      actions.setLoading("");
    }
  }

  async function handleSampleDownload(sampleId, sampleName) {
    try {
      const blob = await api.downloadSample(sampleId);
      downloadBlob(blob, `${sampleId}.csv`);
      actions.setMessage({
        text: `${sampleName} downloaded. You can upload it in the dataset workflow.`,
        tone: "positive",
      });
    } catch (error) {
      actions.setMessage({ text: error.detail || error.message, tone: "negative" });
    }
  }

  return (
    <>
      <div className="grid-two">
        <SectionCard
          title="1. Upload a dataset"
          subtitle="CSV and Excel files are supported. Suggested protected attributes appear automatically after upload."
        >
          <form className="stack-form" onSubmit={handleDatasetUpload}>
            <label className="field-block">
              <span className="field-label">Data file</span>
              <input id="dataset-file" className="text-input file-input" type="file" accept=".csv,.xlsx,.xls" />
            </label>
            <button className="button-primary" disabled={loading === "upload"} type="submit">
              {loading === "upload" ? "Uploading..." : "Upload dataset"}
            </button>
          </form>

          {uploadData ? (
            <div className="detail-stack">
              <div className="pill-row">
                <StatusBadge label={currentJob?.status || "uploaded"} />
                <span>{uploadData.row_count} rows loaded</span>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Column</th>
                      <th>Type</th>
                      <th>Missing</th>
                      <th>Unique</th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns.map((column) => (
                      <tr key={column.name}>
                        <td>{column.name}</td>
                        <td>{column.dtype}</td>
                        <td>{column.null_count}</td>
                        <td>{column.unique_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard
          title="Sample datasets"
          subtitle="These are synthetic examples with known bias patterns so you can test the full workflow quickly."
        >
          <div className="sample-list">
            {samples.map((sample) => (
              <article className="sample-card" key={sample.id}>
                <div>
                  <h3>{sample.name}</h3>
                  <p>{sample.description}</p>
                  <p className="sample-meta">
                    {sample.rows} rows · Known patterns: {sample.known_biases.join(", ")}
                  </p>
                </div>
                <button className="button-secondary" onClick={() => handleSampleDownload(sample.id, sample.name)} type="button">
                  Download CSV
                </button>
              </article>
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="2. Describe the audit"
        subtitle="This setup is usually done once by a technical owner. After that, later users can rerun and review results more easily."
      >
        <form className="stack-form" onSubmit={handleConfigureDataset}>
          <div className="form-grid">
            <label className="field-block">
              <span className="field-label">Organization</span>
              <input className="text-input" value={datasetForm.org_name} onChange={(event) => actions.updateDatasetField("org_name", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">System or model name</span>
              <input className="text-input" value={datasetForm.model_name} onChange={(event) => actions.updateDatasetField("model_name", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Domain</span>
              <input className="text-input" placeholder="Hiring, lending, education..." value={datasetForm.domain} onChange={(event) => actions.updateDatasetField("domain", event.target.value)} />
            </label>
            <label className="field-block">
              <span className="field-label">Outcome column</span>
              <select className="select-input" disabled={!datasetReadyForConfigure} value={datasetForm.outcome_column} onChange={(event) => actions.updateDatasetField("outcome_column", event.target.value)}>
                <option value="">Choose one</option>
                {columns.map((column) => (
                  <option key={column.name} value={column.name}>
                    {column.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-block">
              <span className="field-label">Prediction column (optional)</span>
              <select className="select-input" disabled={!datasetReadyForConfigure} value={datasetForm.prediction_column} onChange={(event) => actions.updateDatasetField("prediction_column", event.target.value)}>
                <option value="">No prediction column</option>
                {columns.map((column) => (
                  <option key={column.name} value={column.name}>
                    {column.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-block">
              <span className="field-label">Favorable outcome value</span>
              <input className="text-input" value={datasetForm.favorable_outcome} onChange={(event) => actions.updateDatasetField("favorable_outcome", event.target.value)} />
            </label>
          </div>

          {uploadData?.suggested_protected_attributes?.length ? (
            <div className="hint-box">
              <strong>Suggested protected attributes</strong>
              <p>{uploadData.suggested_protected_attributes.map(suggestionText).join(" · ")}</p>
            </div>
          ) : null}

          <div className="checkbox-grid">
            {columns.map((column) => (
              <label key={column.name} className={`check-card${selectedColumnOptions.has(column.name) ? " check-card-active" : ""}`}>
                <input checked={selectedColumnOptions.has(column.name)} onChange={() => toggleAttribute(column.name)} type="checkbox" />
                <span>{column.name}</span>
              </label>
            ))}
          </div>

          {selectedAttributes.length ? (
            <div className="form-grid">
              {selectedAttributes.map((attribute) => (
                <label className="field-block" key={attribute}>
                  <span className="field-label">{attribute} reference group (optional)</span>
                  <input
                    className="text-input"
                    placeholder="Example: Male, Urban, General"
                    value={referenceGroups[attribute] || ""}
                    onChange={(event) =>
                      actions.setReferenceGroups((current) => ({
                        ...current,
                        [attribute]: event.target.value,
                      }))
                    }
                  />
                </label>
              ))}
            </div>
          ) : null}

          <button className="button-primary" disabled={!datasetReadyForConfigure || loading === "configure"} type="submit">
            {loading === "configure" ? "Saving..." : "Save setup"}
          </button>
        </form>
      </SectionCard>

      <SectionCard
        title="3. Optional model attachment and checks"
        subtitle="Attach a compatible model artifact for stronger root-cause hints, then run the quality gate before the audit."
      >
        <div className="form-grid">
          <label className="field-block">
            <span className="field-label">Model artifact (.pkl, .pickle, .joblib)</span>
            <input className="text-input file-input" type="file" onChange={(event) => actions.setModelFile(event.target.files?.[0] || null)} />
          </label>
          <div className="action-line">
            <button className="button-secondary" disabled={!datasetReadyForAudit || loading === "model"} onClick={handleModelUpload} type="button">
              {loading === "model" ? "Uploading..." : "Attach model"}
            </button>
            <button className="button-primary" disabled={!datasetReadyForAudit || loading === "quality"} onClick={handleQualityCheck} type="button">
              {loading === "quality" ? "Checking..." : "Run quality check"}
            </button>
          </div>
        </div>

        {qualityReport ? (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Check</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {qualityReport.checks.map((item, index) => (
                  <tr key={`${item.check}-${index}`}>
                    <td>
                      <StatusBadge label={item.status} />
                    </td>
                    <td>{item.check.replace(/_/g, " ")}</td>
                    <td>{item.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <div className="action-line">
          <button className="button-secondary" disabled={!datasetReadyForAudit || loading === "audit"} onClick={handleRunAudit} type="button">
            {loading === "audit" ? "Running..." : "Run audit"}
          </button>
          <button className="button-primary" disabled={!state.auditResults || loading === "report"} onClick={handleGenerateReport} type="button">
            {loading === "report" ? "Generating..." : "Generate report"}
          </button>
        </div>
      </SectionCard>
    </>
  );
}
