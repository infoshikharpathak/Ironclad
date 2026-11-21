# Ironclad Bank

Fictional bank application — PostgreSQL + FastAPI + React, all running locally via Docker Compose.

## Quick Start

```bash
docker compose up --build
```

Then open **http://localhost:3000**.

- **Dashboard**: view accounts and recent transactions
- **Transfer**: move money between checking ↔ savings with OTP confirmation
- **Reset Demo**: restore seed balances ($10,000 checking, $5,000 savings)

## Architecture

```
Browser → nginx (port 3000)
            ├─ /        → React SPA
            ├─ /api/*   → FastAPI (bank-service, port 8001)
            └─ /ws/*    → WebSocket (bank-service)
                              ↕
                         PostgreSQL (port 5432)
```

## Development (without Docker)

```bash
# 1. Start Postgres (or use docker compose up db)
# 2. Bank service
cd bank-service
pip install -r requirements.txt
uvicorn app.main:app --port 8001 --reload

# 3. Frontend (Vite dev server proxies /api and /ws to :8001)
cd web
npm install
npm run dev
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/accounts?user_id=` | List accounts |
| GET | `/accounts/{id}?user_id=` | Single account |
| GET | `/accounts/{id}/transactions?user_id=` | Transaction history |
| POST | `/accounts/reset?user_id=` | Reset demo balances |
| POST | `/transfers/initiate` | Start a transfer (returns OTP) |
| POST | `/transfers/{id}/confirm` | Confirm with OTP |
| GET | `/transfers/{id}/status?user_id=` | Transfer status |
| WS | `/ws/{user_id}` | Real-time notifications |
