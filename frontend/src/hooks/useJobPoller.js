import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Custom hook that polls a job's status while it is queued or running.
 *
 * Usage:
 *   const { status, isRunning, isComplete, isFailed } = useJobPoller(api, jobId);
 *
 * Automatically stops polling when the job reaches a terminal state.
 */
export default function useJobPoller(api, jobId, { intervalMs = 3000 } = {}) {
  const [status, setStatus] = useState(null);
  const [startedAt, setStartedAt] = useState(null);
  const timerRef = useRef(null);

  const poll = useCallback(async () => {
    if (!jobId || !api) return;
    try {
      const data = await api.getJobStatus(jobId);
      setStatus(data.status);
      setStartedAt(data.started_at);

      // Stop polling on terminal states
      const terminal = ["complete", "failed", "reported", "archived"];
      if (terminal.includes(data.status)) {
        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }
    } catch {
      // Silently ignore polling failures
    }
  }, [api, jobId]);

  useEffect(() => {
    if (!jobId) {
      setStatus(null);
      return;
    }

    // Initial poll
    poll();

    // Start interval
    timerRef.current = setInterval(poll, intervalMs);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [jobId, poll, intervalMs]);

  return {
    status,
    startedAt,
    isRunning: status === "running" || status === "queued",
    isComplete: status === "complete",
    isFailed: status === "failed",
  };
}
