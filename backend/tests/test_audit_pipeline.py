from io import BytesIO
import pickle

import pandas as pd
from fastapi.testclient import TestClient
from sklearn.linear_model import LogisticRegression

from app.main import app


client = TestClient(app)


def _train_logistic_model() -> LogisticRegression:
    frame = pd.DataFrame({"experience": [8, 7, 6, 5, 6, 4, 3, 2]})
    target = [1, 1, 1, 1, 1, 0, 0, 0]
    model = LogisticRegression(max_iter=1000)
    model.fit(frame, target)
    return model


def test_file_audit_report_and_mitigation_flow() -> None:
    csv_content = """gender,region,experience,hired,model_decision
Male,Urban,8,1,1
Male,Urban,7,1,1
Male,Rural,6,1,1
Male,Rural,5,1,1
Female,Urban,6,1,0
Female,Urban,4,0,0
Female,Rural,3,0,0
Female,Rural,2,0,0
"""
    upload_response = client.post(
        "/api/upload",
        data={"mode": "prediction"},
        files={"file": ("audit.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    configure_response = client.post(
        "/api/configure",
        json={
            "job_id": job_id,
            "outcome_column": "hired",
            "prediction_column": "model_decision",
            "favorable_outcome": 1,
            "protected_attributes": ["gender", "region"],
            "org_name": "Acme",
            "model_name": "Hiring",
            "domain": "hiring",
        },
    )
    assert configure_response.status_code == 200

    model_bytes = pickle.dumps(_train_logistic_model())
    model_upload_response = client.post(
        "/api/model/upload",
        data={"job_id": job_id},
        files={"file": ("model.pkl", BytesIO(model_bytes), "application/octet-stream")},
    )
    assert model_upload_response.status_code == 200

    run_response = client.post("/api/audit/run", json={"job_id": job_id})
    assert run_response.status_code == 200

    result_response = client.get(f"/api/audit/{job_id}")
    assert result_response.status_code == 200
    assert "gender" in result_response.json()["results"]
    assert "gender" in result_response.json()["root_cause_analysis"]

    report_response = client.post("/api/report/generate", json={"job_id": job_id})
    assert report_response.status_code == 200
    assert report_response.json()["mitigation_cards"]
    assert report_response.json()["mitigation_cards"][0]["tradeoff_options"]

    mitigation_response = client.get(f"/api/mitigate/{job_id}/download", params={"method": "reweight"})
    assert mitigation_response.status_code == 200
    assert "sample_weight" in mitigation_response.text

    pdf_response = client.get(f"/api/report/{job_id}/pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"


def test_aggregate_history_compare_and_samples() -> None:
    aggregate_one = client.post(
        "/api/aggregate",
        json={
            "org_name": "Acme Bank",
            "model_name": "Loan Model v1",
            "domain": "lending",
            "attribute_name": "Region",
            "groups": [
                {"name": "Urban", "total": 100, "favorable": 80},
                {"name": "Rural", "total": 100, "favorable": 40},
            ],
        },
    )
    aggregate_two = client.post(
        "/api/aggregate",
        json={
            "org_name": "Acme Bank",
            "model_name": "Loan Model v2",
            "domain": "lending",
            "attribute_name": "Region",
            "groups": [
                {"name": "Urban", "total": 100, "favorable": 80},
                {"name": "Rural", "total": 100, "favorable": 60},
            ],
        },
    )
    job_one = aggregate_one.json()["job_id"]
    job_two = aggregate_two.json()["job_id"]

    assert client.post("/api/audit/run", json={"job_id": job_one}).status_code == 200
    assert client.post("/api/audit/run", json={"job_id": job_two}).status_code == 200

    compare_response = client.get("/api/history/compare", params={"job_id_old": job_one, "job_id_new": job_two})
    assert compare_response.status_code == 200
    assert compare_response.json()["comparisons"]

    samples_response = client.get("/api/samples")
    assert samples_response.status_code == 200
    assert len(samples_response.json()["datasets"]) >= 3
