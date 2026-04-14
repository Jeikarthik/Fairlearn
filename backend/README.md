# FairLens Backend

This directory contains the FastAPI backend for FairLens.

For full project documentation, use:

- [`../docs/PROJECT_DOCUMENTATION.md`](../docs/PROJECT_DOCUMENTATION.md)

That document covers:

- backend architecture
- API routes
- service layout
- setup and environment variables
- testing
- current limitations

Backend quick start:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
uvicorn app.main:app --reload
```
