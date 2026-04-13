from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException, UploadFile, status

from app.constants import SUPPORTED_UPLOAD_SUFFIXES
from app.core.config import get_settings
from app.schemas.upload import ColumnProfile
from app.services.attribute_detector import detect_protected_attributes
from app.services.normalization import normalize_dataframe


def save_upload(upload: UploadFile) -> Path:
    settings = get_settings()
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{suffix}'. Upload CSV or Excel.",
        )

    destination = settings.upload_dir / f"{uuid4()}{suffix}"
    max_size_bytes = settings.max_upload_size_mb * 1024 * 1024
    total_written = 0

    upload.file.seek(0)
    with destination.open("wb") as output:
        while chunk := upload.file.read(1024 * 1024):
            total_written += len(chunk)
            if total_written > max_size_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds the {settings.max_upload_size_mb}MB limit.",
                )
            output.write(chunk)

    upload.file.seek(0)
    return destination


def read_tabular_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    raise ValueError(f"Unsupported file type: {suffix}")


def build_upload_summary(df: pd.DataFrame) -> dict[str, object]:
    normalized = normalize_dataframe(df)
    preview = normalized.head(10).replace({pd.NA: None}).where(pd.notna(normalized.head(10)), None)
    columns = [
        ColumnProfile(
            name=str(column),
            dtype=str(normalized[column].dtype),
            null_count=int(normalized[column].isna().sum()),
            unique_count=int(normalized[column].nunique(dropna=True)),
            sample_values=_sample_values(normalized[column]),
        ).model_dump()
        for column in normalized.columns
    ]
    suggestions = [item.model_dump() for item in detect_protected_attributes(normalized)]
    return {
        "row_count": int(len(normalized.index)),
        "preview": json.loads(preview.to_json(orient="records")),
        "columns": columns,
        "suggested_protected_attributes": suggestions,
    }


def _sample_values(series: pd.Series) -> list[object]:
    samples = series.dropna().astype(object).head(5).tolist()
    return [None if pd.isna(value) else value for value in samples]
