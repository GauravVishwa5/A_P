# Amrutam Telemedicine Platform — Backend

A production-grade, highly resilient backend for the **Amrutam Telemedicine Platform** built with **Python 3.12**, **FastAPI**, **SQLAlchemy 2.0 (Async)**, **PostgreSQL 16**, **Redis 7**, and **ARQ**.

---

## Key System Invariants & Highlights

- **Modular Monolith**: Strict domain isolation (`auth`, `users`, `doctors`, `availability`, `consultations`, `prescriptions`, `payments`, `notifications`, `audit`) avoiding distributed microservice complexity.
- **Atomic Booking Concurrency**: Pessimistic slot locking (`SELECT ... FOR UPDATE`) backed by a database-level partial unique index (`uq_consultations_slot_active`) that deterministically prevents double bookings.
- **Validated 100-Racer Concurrency Benchmark**: Verified under 100 simultaneous concurrent booking requests for the identical slot $\rightarrow$ exactly **1 × 201 Created**, **99 × 409 Conflict**, and **0 database anomalies**.
- **Decoupled Saga Payments**: Zero open database transactions during external gateway calls, timeout handling retaining state for background reconciliation, and deterministic idempotency replay.
- **Enterprise Security**: Argon2id password hashing, RFC 6238 TOTP MFA, rotating refresh tokens with cryptographic family revocation upon replay, RFC 7807 problem details, and full IDOR data isolation.
- **Observability & Health Probes**: `/health` (liveness), `/ready` (readiness checking PostgreSQL & Redis), `/metrics` (Prometheus telemetry), OpenTelemetry distributed tracing, and sensitive data log masking.

---

## Technology Stack

| Layer | Component | Technology |
| :--- | :--- | :--- |
| **Runtime** | Language & Web Framework | Python 3.12, FastAPI, Uvicorn |
| **Primary Database** | Authoritative ACID Store | PostgreSQL 16 (Async via `asyncpg`, SQLAlchemy 2.0) |
| **Cache & Queue** | Ephemeral State & Background Jobs | Redis 7, ARQ Worker |
| **Migrations** | Database Schema Evolution | Alembic |
| **Reverse Proxy** | Security & Request Routing | Nginx 1.25 Alpine |
| **Observability** | Telemetry & Tracing | Prometheus, OpenTelemetry SDK, Grafana |
| **Quality & Types** | Static Analysis & Testing | Ruff, Mypy (Strict), Bandit, Pytest (Async) |

---

## Quickstart Guide

### Option A: Complete Docker Compose Environment (Recommended)

Starts all 7 services (`nginx`, `api`, `worker`, `postgres`, `redis`, `prometheus`, `grafana`):

```bash
# 1. Clone repository and start all containers
docker compose up -d --build

# 2. Verify all services are healthy
docker compose ps

# 3. Access endpoints
# - API (via Nginx): http://localhost/docs
# - Prometheus:     http://localhost:9090
# - Grafana:        http://localhost:3000 (admin / admin)
```

### Option B: Local Python Development Environment

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -e .
pip install ruff mypy bandit pytest pytest-asyncio pytest-cov

# 3. Run database migrations
alembic upgrade head

# 4. Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start Background Worker (in another terminal)
python -m app.workers.worker
```

---

## Verification & Testing Suite

The repository features comprehensive automated test coverage across unit, API integration, and concurrent race conditions.

```bash
# Run the entire test suite (39 tests)
pytest -v

# Run the 100-Concurrent-Booking Race Benchmark
pytest tests/concurrency/test_booking_race.py -v

# Code Quality Checks
ruff check .
ruff format --check .
mypy app tests

# Security Vulnerability Audit
bandit -r app -ll -ii
```

---

## Documentation Directory (`docs/`)

Detailed design and architecture specifications:

- [System Architecture](docs/architecture.md)
- [Booking Sequence & State Machine](docs/booking-sequence.md)
- [Database ER Diagram](docs/er-diagram.md)
- [STRIDE Threat Model](docs/threat-model.md)
- [Production Security Checklist](docs/security-checklist.md)
- [Concurrency & Performance Benchmark Report](docs/performance-report.md)
- [API Demonstration & Walkthrough Script](docs/demo-script.md)
- [Postman Collection](docs/amrutam-telemedicine.postman_collection.json) (Auto-Bearer token on Register/Login)
