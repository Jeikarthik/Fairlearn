import pandas as pd

from app.services.quality_gate import run_quality_gate


def test_quality_gate_flags_small_groups_and_ground_truth_bias() -> None:
    df = pd.DataFrame(
        {
            "gender": ["Male"] * 40 + ["Female"] * 10,
            "decision": [1] * 35 + [0] * 5 + [1] * 2 + [0] * 8,
            "prediction": [1] * 50,
        }
    )

    report = run_quality_gate(
        df,
        {
            "outcome_column": "decision",
            "prediction_column": "prediction",
            "favorable_outcome": 1,
            "protected_attributes": ["gender"],
        },
    )

    check_names = [item["check"] for item in report["checks"]]
    assert report["overall_status"] == "pass_with_warnings"
    assert "group_size" in check_names
    assert "ground_truth_reliability" in check_names
