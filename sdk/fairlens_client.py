"""FairLens Python SDK — programmatic access to the FairLens API.

Install:
    pip install requests pandas  # lightweight — no heavy ML deps needed

Quick-start:
    from fairlens_client import FairLensClient
    import pandas as pd

    client = FairLensClient("http://localhost:8000/api")

    df = pd.read_csv("my_data.csv")
    results = client.audit(
        df,
        outcome_column="hired",
        protected_attributes=["gender", "region"],
        favorable_outcome=1,
        domain="employment",
    )
    print(results["results"]["gender"]["metrics"])

    # Or audit from aggregate counts (no raw data required):
    results = client.audit_aggregate(
        attribute_name="Region",
        groups=[
            {"name": "Urban", "total": 500, "favorable": 400},
            {"name": "Rural", "total": 500, "favorable": 200},
        ],
        domain="lending",
    )
"""
from __future__ import annotations

import io
import time
from typing import Any

try:
    import requests
except ImportError as exc:
    raise ImportError(
        "FairLens SDK requires 'requests'. Install it with: pip install requests"
    ) from exc


class FairLensError(Exception):
    """Raised when the FairLens API returns an error response."""
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FairLensClient:
    """Thin Python wrapper around the FairLens REST API.

    Args:
        base_url:    API base URL, e.g. "http://localhost:8000/api"
        api_token:   Bearer token if auth is enabled
        timeout:     HTTP request timeout in seconds (default 30)
        poll_interval: Seconds between status polls when waiting for audit (default 3)
        max_wait:    Maximum seconds to wait for an audit to complete (default 300)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000/api",
        *,
        api_token: str | None = None,
        timeout: int = 30,
        poll_interval: int = 3,
        max_wait: int = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait
        self._session = requests.Session()
        if api_token:
            self._session.headers["Authorization"] = f"Bearer {api_token}"

    # ── High-level convenience methods ────────────────────────────

    def audit(
        self,
        df,
        *,
        outcome_column: str,
        protected_attributes: list[str],
        favorable_outcome: Any,
        prediction_column: str | None = None,
        domain: str = "general",
        org_name: str = "SDK",
        model_name: str = "SDK Audit",
        wait: bool = True,
    ) -> dict[str, Any]:
        """Upload a DataFrame, configure, and run a full audit.

        Args:
            df:                    pandas DataFrame with the data to audit
            outcome_column:        Column name of the ground-truth outcome
            protected_attributes:  List of protected attribute column names
            favorable_outcome:     Value that represents the favorable outcome
            prediction_column:     Optional model prediction column
            domain:                Threshold preset: general|employment|lending|healthcare|education
            org_name:              Organisation label in the report
            model_name:            System name label in the report
            wait:                  If True, block until the audit completes and return results

        Returns:
            Audit result dict (same schema as GET /audit/{job_id})
        """
        try:
            import pandas as pd
        except ImportError as exc:
            raise ImportError("audit() requires pandas. Install with: pip install pandas") from exc

        # Serialise DataFrame to CSV bytes
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        buf.seek(0)

        # 1. Upload
        mode = "prediction" if prediction_column else "dataset"
        upload = self._post_multipart(
            "/upload",
            data={"mode": mode},
            files={"file": ("data.csv", buf, "text/csv")},
        )
        job_id = upload["job_id"]

        # 2. Configure
        self._post_json("/configure", {
            "job_id": job_id,
            "outcome_column": outcome_column,
            "prediction_column": prediction_column,
            "protected_attributes": protected_attributes,
            "favorable_outcome": favorable_outcome,
            "domain": domain,
            "org_name": org_name,
            "model_name": model_name,
        })

        # 3. Run
        self._post_json("/audit/run", {"job_id": job_id})

        if not wait:
            return {"job_id": job_id, "status": "queued"}

        return self._wait_for_results(job_id)

    def audit_aggregate(
        self,
        *,
        attribute_name: str,
        groups: list[dict[str, Any]],
        domain: str = "general",
        org_name: str = "SDK",
        model_name: str = "SDK Audit",
        wait: bool = True,
    ) -> dict[str, Any]:
        """Submit an aggregate (count-based) audit without raw data.

        Args:
            attribute_name: Name of the protected attribute
            groups:         List of {"name": str, "total": int, "favorable": int}
            domain:         Threshold preset
            org_name:       Organisation label
            model_name:     System label
            wait:           Block until complete

        Returns:
            Audit result dict
        """
        agg = self._post_json("/aggregate", {
            "attribute_name": attribute_name,
            "groups": groups,
            "domain": domain,
            "org_name": org_name,
            "model_name": model_name,
        })
        job_id = agg["job_id"]
        self._post_json("/audit/run", {"job_id": job_id})
        if not wait:
            return {"job_id": job_id, "status": "queued"}
        return self._wait_for_results(job_id)

    def get_results(self, job_id: str) -> dict[str, Any]:
        """Fetch audit results for a completed job."""
        return self._get(f"/jobs/{job_id}")

    def get_status(self, job_id: str) -> dict[str, Any]:
        """Fetch the lightweight status of a job (fast polling endpoint)."""
        return self._get(f"/jobs/{job_id}/status")

    def generate_report(self, job_id: str) -> dict[str, Any]:
        """Generate a plain-language report for a completed audit."""
        return self._post_json("/report/generate", {"job_id": job_id})

    def download_report_pdf(self, job_id: str) -> bytes:
        """Download the PDF audit report. Returns raw bytes."""
        resp = self._session.get(
            f"{self.base_url}/report/{job_id}/pdf",
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.content

    def regulatory_report(self, job_id: str, report_type: str) -> dict[str, Any]:
        """Generate a regulatory compliance report.

        report_type: nyc_ll144 | eu_ai_act | ecoa_adverse_action
        """
        return self._get(f"/report/{job_id}/regulatory/{report_type}")

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all audit jobs in history."""
        return self._get("/history").get("audits", [])

    def compare_jobs(self, old_job_id: str, new_job_id: str) -> dict[str, Any]:
        """Compare fairness metrics between two audit runs."""
        return self._get(f"/history/compare?job_id_old={old_job_id}&job_id_new={new_job_id}")

    def add_alert_rule(self, monitor_job_id: str, rule: dict[str, Any]) -> dict[str, Any]:
        """Add a drift alert rule to a monitor job."""
        return self._post_json(f"/monitor/{monitor_job_id}/alerts", rule)

    def list_alert_rules(self, monitor_job_id: str) -> list[dict[str, Any]]:
        """List alert rules for a monitor job."""
        return self._get(f"/monitor/{monitor_job_id}/alerts").get("rules", [])

    def delete_alert_rule(self, monitor_job_id: str, rule_id: str) -> dict[str, Any]:
        """Delete an alert rule by ID."""
        resp = self._session.delete(
            f"{self.base_url}/monitor/{monitor_job_id}/alerts/{rule_id}",
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    def set_schedule(self, job_id: str, *, enabled: bool = True, interval_hours: int = 24) -> dict[str, Any]:
        """Enable or disable scheduled re-auditing for a job."""
        return self._post_json(f"/jobs/{job_id}/schedule", {
            "enabled": enabled,
            "interval_hours": interval_hours,
        })

    # ── Polling helper ─────────────────────────────────────────────

    def _wait_for_results(self, job_id: str) -> dict[str, Any]:
        terminal = {"complete", "reported", "failed", "archived"}
        elapsed = 0
        while elapsed < self.max_wait:
            status = self.get_status(job_id)
            if status.get("status") in terminal:
                break
            time.sleep(self.poll_interval)
            elapsed += self.poll_interval

        job = self.get_results(job_id)
        if job.get("status") == "failed":
            raise FairLensError(f"Audit {job_id} failed: {job.get('results', {}).get('error', 'unknown error')}")
        return job

    # ── Low-level request helpers ──────────────────────────────────

    def _get(self, path: str) -> Any:
        resp = self._session.get(f"{self.base_url}{path}", timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def _post_json(self, path: str, body: dict[str, Any]) -> Any:
        resp = self._session.post(
            f"{self.base_url}{path}",
            json=body,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    def _post_multipart(self, path: str, *, data: dict, files: dict) -> Any:
        resp = self._session.post(
            f"{self.base_url}{path}",
            data=data,
            files=files,
            timeout=self.timeout,
        )
        self._raise_for_status(resp)
        return resp.json()

    @staticmethod
    def _raise_for_status(resp: requests.Response) -> None:
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:  # noqa: BLE001
                detail = resp.text
            raise FairLensError(f"HTTP {resp.status_code}: {detail}", status_code=resp.status_code)
