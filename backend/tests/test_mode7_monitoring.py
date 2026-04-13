from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_mode7_monitoring_generates_non_technical_alerts() -> None:
    setup_response = client.post(
        "/api/monitor/setup",
        json={
            "org_name": "Acme Corp",
            "system_name": "Hiring Model",
            "domain": "hiring",
            "protected_attributes": ["gender"],
            "prediction_field": "decision",
            "favorable_outcome": 1,
            "thresholds": {
                "demographic_parity_gap": 0.10,
                "disparate_impact_ratio": 0.80,
                "alert_window_size": 8,
            },
        },
    )
    assert setup_response.status_code == 200
    job_id = setup_response.json()["job_id"]

    webhook_response = client.post(
        f"/api/webhook/predict/{job_id}",
        json={
            "records": [
                {"values": {"gender": "Male", "decision": 1}},
                {"values": {"gender": "Male", "decision": 1}},
                {"values": {"gender": "Male", "decision": 1}},
                {"values": {"gender": "Male", "decision": 1}},
                {"values": {"gender": "Female", "decision": 0}},
                {"values": {"gender": "Female", "decision": 0}},
                {"values": {"gender": "Female", "decision": 0}},
                {"values": {"gender": "Female", "decision": 1}},
            ]
        },
    )

    payload = webhook_response.json()
    assert webhook_response.status_code == 200
    assert payload["status"] == "alerting"
    assert payload["alerts"]
    assert "warning" in payload["insight_headline"].lower() or "attention" in payload["insight_headline"].lower()

