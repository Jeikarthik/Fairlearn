# FairLens Env and Credentials Guide

This project uses three env files in practice:

- Root: [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
- Backend: [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
- Frontend: [`frontend/.env`](/C:/Apps/hack2skill/Fairlearn/frontend/.env)

## 1. What you must provide

### Required for AI reports

- `FAIRLENS_GEMINI_API_KEY` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
- `GEMINI_API_KEY` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env) if you run the project through Docker Compose

Use the same Gemini key value in both places when you want local backend runs and Docker runs to behave the same way.

### Required if you enable authentication

- `FAIRLENS_JWT_SECRET_KEY` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
- `FAIRLENS_JWT_SECRET_KEY` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env) for Docker Compose

Generate a strong secret with:

```powershell
openssl rand -hex 32
```

### Required if you switch to PostgreSQL

- `POSTGRES_USER` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
- `POSTGRES_PASSWORD` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
- `POSTGRES_DB` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
- `FAIRLENS_DATABASE_URL` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env) if you run the backend outside Docker

For local non-Docker backend runs, use a URL like:

```env
FAIRLENS_DATABASE_URL=postgresql+psycopg2://fairlens:YOUR_PASSWORD@localhost:5432/fairlens
```

## 2. Optional credentials / endpoints

- `FAIRLENS_CELERY_BROKER_URL` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env) if you want Redis-backed background workers locally
- `OTEL_ENDPOINT` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env) only if you want OpenTelemetry export

## 3. Not credentials, but still important

- `FAIRLENS_AUTH_DISABLED` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
  - `true` for fastest local development
  - `false` when testing login/auth flows
- `VITE_API_BASE_URL` in [`frontend/.env`](/C:/Apps/hack2skill/Fairlearn/frontend/.env)
  - Default local value is already correct for this repo
- `FAIRLENS_CORS_ORIGINS` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
  - Add your frontend origin here if you change ports/domains

## 4. Quick setup

### Local development without Docker

1. Fill `FAIRLENS_GEMINI_API_KEY` in [`backend/.env`](/C:/Apps/hack2skill/Fairlearn/backend/.env)
2. Leave `FAIRLENS_AUTH_DISABLED=true` unless you want auth testing
3. Keep SQLite as the default `FAIRLENS_DATABASE_URL`
4. Keep [`frontend/.env`](/C:/Apps/hack2skill/Fairlearn/frontend/.env) as-is

### Docker Compose

1. Fill `POSTGRES_PASSWORD` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
2. Fill `GEMINI_API_KEY` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
3. Fill `FAIRLENS_JWT_SECRET_KEY` in [`.env`](/C:/Apps/hack2skill/Fairlearn/.env)
4. Run:

```powershell
docker-compose up --build
```
