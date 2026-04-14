function normalizeBaseUrl(value) {
  return value.replace(/\/+$/, "");
}

function buildError(message, detail) {
  const error = new Error(detail || message);
  error.detail = detail;
  return error;
}

export function createApiClient(apiBase) {
  const base = normalizeBaseUrl(apiBase);

  async function request(path, options = {}) {
    const response = await fetch(`${base}${path}`, options);
    const contentType = response.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");
    const payload = isJson ? await response.json() : await response.text();

    if (!response.ok) {
      if (isJson && payload?.detail) {
        throw buildError("Request failed", payload.detail);
      }
      throw buildError("Request failed", typeof payload === "string" ? payload : response.statusText);
    }

    return payload;
  }

  async function download(path) {
    const response = await fetch(`${base}${path}`);
    if (!response.ok) {
      const payload = await response.text();
      throw buildError("Download failed", payload || response.statusText);
    }
    return response.blob();
  }

  return {
    health: () => request("/health"),
    uploadDataset(file, mode = "prediction") {
      const formData = new FormData();
      formData.append("mode", mode);
      formData.append("file", file);
      return request("/upload", { method: "POST", body: formData });
    },
    aggregateInput(payload) {
      return request("/aggregate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    configure(payload) {
      return request("/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    uploadModel(jobId, file) {
      const formData = new FormData();
      formData.append("job_id", jobId);
      formData.append("file", file);
      return request("/model/upload", { method: "POST", body: formData });
    },
    qualityCheck(jobId) {
      return request("/quality-check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });
    },
    runAudit(jobId) {
      return request("/audit/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });
    },
    getAudit(jobId) {
      return request(`/audit/${jobId}`);
    },
    getJob(jobId) {
      return request(`/jobs/${jobId}`);
    },
    listHistory() {
      return request("/history");
    },
    compareHistory(oldId, newId) {
      const params = new URLSearchParams({ job_id_old: oldId, job_id_new: newId });
      return request(`/history/compare?${params.toString()}`);
    },
    getSamples() {
      return request("/samples");
    },
    downloadSample(sampleId) {
      return download(`/samples/${sampleId}/download`);
    },
    configureApiProbe(payload) {
      return request("/probe/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    runApiProbe(jobId, mockOutcomes) {
      return request("/probe/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, mock_outcomes: mockOutcomes?.length ? mockOutcomes : null }),
      });
    },
    getApiProbe(jobId) {
      return request(`/probe/${jobId}`);
    },
    setupNlpProbe(payload) {
      return request("/nlp-probe/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    runNlpProbe(jobId, mockOutcomes) {
      return request("/nlp-probe/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, mock_outcomes: mockOutcomes?.length ? mockOutcomes : null }),
      });
    },
    getNlpProbe(jobId) {
      return request(`/nlp-probe/${jobId}`);
    },
    setupMonitoring(payload) {
      return request("/monitor/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    sendMonitoringRecords(jobId, records) {
      return request(`/webhook/predict/${jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          records: records.map((values) => ({ values })),
        }),
      });
    },
    getMonitoring(jobId) {
      return request(`/monitor/${jobId}`);
    },
    generateReport(jobId) {
      return request("/report/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId }),
      });
    },
    downloadReportPdf(jobId) {
      return download(`/report/${jobId}/pdf`);
    },
    downloadMitigation(jobId, method) {
      return download(`/mitigate/${jobId}/download?method=${encodeURIComponent(method)}`);
    },
  };
}
