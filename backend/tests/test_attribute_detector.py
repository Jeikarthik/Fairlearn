import pandas as pd

from app.services.attribute_detector import detect_protected_attributes


def test_attribute_detector_prefers_name_and_value_signals() -> None:
    df = pd.DataFrame(
        {
            "gender": ["male", "female", "female"],
            "district_type": ["Urban", "Rural", "Urban"],
            "department": ["Engineering", "HR", "Sales"],
        }
    )

    suggestions = detect_protected_attributes(df)
    by_column = {item.column: item for item in suggestions}

    assert by_column["gender"].confidence == "high"
    assert by_column["district_type"].confidence in {"high", "low"}
    assert "department" in by_column
