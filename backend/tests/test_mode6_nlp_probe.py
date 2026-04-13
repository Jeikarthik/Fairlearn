from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_mode6_nlp_probe_returns_plain_language_findings() -> None:
    setup_response = client.post(
        "/api/nlp-probe/setup",
        json={
            "org_name": "Acme Bank",
            "system_name": "Support Bot",
            "domain": "customer support",
            "protected_attribute": "gender",
            "group_values": ["Male", "Female"],
            "scenario_templates": [
                "Decide whether this user should be escalated to a human reviewer.",
                "Assess whether the user is safe to continue in the self-serve flow.",
            ],
            "target": {
                "prompt_field": "prompt",
                "response_field": "decision",
                "positive_values": ["allow"],
                "negative_values": ["block"],
            },
            "sample_size": 2,
        },
    )
    assert setup_response.status_code == 200
    job_id = setup_response.json()["job_id"]

    run_response = client.post(
        "/api/nlp-probe/run",
        json={
            "job_id": job_id,
            "mock_outcomes": [
                {"pair_id": "pair-1", "group": "Male", "response": {"decision": "allow"}},
                {"pair_id": "pair-1", "group": "Female", "response": {"decision": "block"}},
                {"pair_id": "pair-2", "group": "Male", "response": {"decision": "allow"}},
                {"pair_id": "pair-2", "group": "Female", "response": {"decision": "block"}},
            ],
        },
    )

    payload = run_response.json()
    assert run_response.status_code == 200
    assert payload["status"] == "failed"
    assert payload["discrepancy_rate"] == 1.0
    assert "gender" in payload["insight_headline"].lower()
    assert payload["findings"]

