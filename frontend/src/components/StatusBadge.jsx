import { statusTone, toTitleCase } from "../utils/format";

export default function StatusBadge({ label, tone }) {
  const resolvedTone = tone || statusTone(label);
  return <span className={`status-badge tone-${resolvedTone}`}>{toTitleCase(label)}</span>;
}
