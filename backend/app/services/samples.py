from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def ensure_sample_datasets(base_dir: Path) -> list[dict[str, str | int | list[str]]]:
    base_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("hiring", "Tech Company Hiring Decisions", 5000, ["gender", "region", "age"]),
        ("loan", "NBFC Loan Approvals", 3000, ["region", "income x region"]),
        ("scholarship", "Government Scholarship Selection", 2000, ["caste_category", "district_type"]),
    ]
    datasets: list[dict[str, str | int | list[str]]] = []
    for sample_id, name, rows, biases in specs:
        path = base_dir / f"{sample_id}.csv"
        if not path.exists():
            _generate_dataset(sample_id, rows).to_csv(path, index=False)
        datasets.append(
            {
                "id": sample_id,
                "name": name,
                "description": f"Synthetic sample for {name.lower()}",
                "rows": rows,
                "known_biases": biases,
                "path": str(path),
            }
        )
    return datasets


def _generate_dataset(sample_id: str, rows: int) -> pd.DataFrame:
    rng = np.random.default_rng(42 + rows)
    if sample_id == "hiring":
        gender = rng.choice(["Male", "Female"], rows, p=[0.52, 0.48])
        region = rng.choice(["Urban", "Rural"], rows, p=[0.6, 0.4])
        age = rng.integers(21, 56, rows)
        base = rng.normal(0.65, 0.15, rows)
        bias = np.where(gender == "Female", -0.12, 0) + np.where(region == "Rural", -0.10, 0) + np.where(age >= 40, -0.08, 0)
        hired = (base + bias > 0.6).astype(int)
        predicted = (base + bias + rng.normal(0, 0.08, rows) > 0.62).astype(int)
        return pd.DataFrame({"gender": gender, "region": region, "age": age, "hired": hired, "model_decision": predicted})
    if sample_id == "loan":
        region = rng.choice(["Urban", "Rural"], rows, p=[0.7, 0.3])
        income = rng.choice(["Low", "Mid", "High"], rows, p=[0.35, 0.45, 0.2])
        caste = rng.choice(["SC", "ST", "OBC", "General"], rows)
        score = rng.normal(650, 70, rows)
        bias = np.where(region == "Rural", -55, 0) + np.where((region == "Rural") & (income == "Low"), -40, 0)
        approved = (score + bias > 620).astype(int)
        predicted = (score + bias + rng.normal(0, 25, rows) > 625).astype(int)
        return pd.DataFrame({"region": region, "income_bracket": income, "caste_category": caste, "credit_score": score, "approved": approved, "model_prediction": predicted})
    district = rng.choice(["Urban", "Rural"], rows, p=[0.55, 0.45])
    caste = rng.choice(["SC", "ST", "OBC", "General"], rows)
    gender = rng.choice(["Male", "Female"], rows)
    score = rng.normal(72, 10, rows)
    bias = np.where(np.isin(caste, ["SC", "ST"]), -7, 0) + np.where(district == "Rural", -4, 0)
    selected = (score + bias > 70).astype(int)
    predicted = (score + bias + rng.normal(0, 4, rows) > 71).astype(int)
    return pd.DataFrame({"gender": gender, "caste_category": caste, "district_type": district, "board_score": score, "selected": selected, "algorithm_decision": predicted})
