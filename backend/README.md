# FairLens Backend

FastAPI service for the FairLens audit workflow. This package currently implements the ingestion and quality-gate foundation:

- upload CSV or Excel datasets
- profile columns and preview data
- auto-suggest likely protected attributes
- save audit configuration
- run a pre-audit quality gate on the configured dataset

Use `uvicorn app.main:app --reload` from this directory after installing dependencies.
