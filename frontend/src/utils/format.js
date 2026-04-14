export function toTitleCase(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatMetric(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return Number(value).toFixed(3);
}

export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Not available";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function parsePrimitive(raw) {
  if (raw === "true") {
    return true;
  }
  if (raw === "false") {
    return false;
  }
  if (raw !== "" && !Number.isNaN(Number(raw))) {
    return Number(raw);
  }
  return raw;
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function statusTone(value) {
  if (["complete", "online", "pass", "pass_with_warnings", "monitoring"].includes(value)) {
    return "positive";
  }
  if (["fail", "offline", "critical", "alerting", "failed"].includes(value)) {
    return "negative";
  }
  return "neutral";
}
