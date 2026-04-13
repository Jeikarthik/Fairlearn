from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_mode5_api_probe_reports_counterfactual_mismatch() -> None:
    setup_response = client.post(
        "/api/probe/configure",
        json={
            "org_name": "Acme Bank",
            "system_name": "Vendor Credit API",
            "domain": "lending",
            "input_schema": {"age": "integer", "income": "float", "gender": "string"},
            "protected_attribute": "gender",
            "group_values": ["Male", "Female"],
            "decision_field": "decision",
            "num_test_pairs": 2,
        },
    )
    assert setup_response.status_code == 200
    job_id = setup_response.json()["job_id"]

    run_response = client.post(
        "/api/probe/run",
        json={
            "job_id": job_id,
            "mock_outcomes": [
                {"pair_id": "probe-1", "group": "Male", "response": {"decision": "approve"}},
                {"pair_id": "probe-1", "group": "Female", "response": {"decision": "deny"}},
                {"pair_id": "probe-2", "group": "Male", "response": {"decision": "approve"}},
                {"pair_id": "probe-2", "group": "Female", "response": {"decision": "approve"}},
            ],
        },
    )

    payload = run_response.json()
    assert run_response.status_code == 200
    assert payload["discrepancy_rate"] == 0.5
    assert payload["findings"]

