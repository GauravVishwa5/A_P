# 🌿 Amrutam Telemedicine Platform — Master Engineering & Architecture Documentation

> **System Version:** 1.0.0 (Production-Ready)  
> **Architecture:** Clean Modular Monolith with Asynchronous Decoupling  
> **Database:** AWS RDS PostgreSQL 16 (Engine: `postgresql+asyncpg` over TLS/SSL)  
> **Cache & Message Broker:** Redis 7 (In-Memory Datastore & ARQ Job Queue)  
> **Compute & Infrastructure:** AWS EC2 (`t2.micro` / `t3.micro`, Ubuntu 24.04 LTS), Nginx Reverse Proxy, Docker Compose  
> **Continuous Integration / Continuous Delivery:** GitHub Actions Automated CI/CD Pipeline  
> **Live Production Server:** `http://34.229.194.135/docs`  
> **Interactive API Documentation:** [Swagger UI](http://34.229.194.135/docs) | [ReDoc](http://34.229.194.135/redoc)

---

## 📑 Table of Contents

1. [Executive Summary & Domain Overview](#1-executive-summary--domain-overview)
2. [Architectural Blueprint & Design Patterns](#2-architectural-blueprint--design-patterns)
3. [Technology Stack & Decision Matrix](#3-technology-stack--decision-matrix)
4. [Directory & Modular Layout](#4-directory--modular-layout)
5. [Database Architecture & Entity Dictionary](#5-database-architecture--entity-dictionary)
6. [Security, Cryptography & Compliance](#6-security-cryptography--compliance)
7. [Deterministic State Machines & Concurrency Controls](#7-deterministic-state-machines--concurrency-controls)
8. [Background Workers & Asynchronous Task Processing](#8-background-workers--asynchronous-task-processing)
9. [Complete API Reference (All 32 Endpoints with Payloads)](#9-complete-api-reference-all-32-endpoints-with-payloads)
10. [Error Handling & RFC 7807 Problem Details Catalog](#10-error-handling--rfc-7807-problem-details-catalog)
11. [Environment Configuration Dictionary](#11-environment-configuration-dictionary)
12. [Testing, Quality Assurance & Concurrency Benchmark](#12-testing-quality-assurance--concurrency-benchmark)
13. [DevOps, Cloud Infrastructure & CI/CD Pipeline](#13-devops-cloud-infrastructure--cicd-pipeline)
14. [Step-by-Step GitHub Actions Setup Guide](#14-step-by-step-github-actions-setup-guide)
15. [Postman Automated Collection & Pre-Seeded Demo Data](#15-postman-automated-collection--pre-seeded-demo-data)
16. [Operations, Runbook & Maintenance Guide](#16-operations-runbook--maintenance-guide)

---

## 1. Executive Summary & Domain Overview

The **Amrutam Telemedicine Platform** is an enterprise-grade backend system engineered specifically for modern Ayurvedic healthcare delivery. In telehealth, reliability, privacy, and data integrity are legal and clinical imperatives rather than optional software metrics.

### Key Clinical & Business Challenges Solved:
- **Zero Double-Booking Guarantee**: Doctor availability slots cannot be oversold under any circumstances, even during peak flash-traffic booking windows.
- **Idempotent Financial Transactions**: Mobile and web clients experiencing transient network disconnects must never trigger duplicate credit card or UPI charges, nor create orphaned consultations.
- **Immutable Clinical Audit Trails**: Prescriptions, diagnoses, and medical consultations must be tamper-proof and traceable to specific certified practitioners (aligned with ABDM / HIPAA requirements).
- **Graceful Fault Tolerance & High Availability**: Redis outages or network degradation must never cause total application downtime. The system employs defensive degradation and fail-open/closed rate limiting.

---

## 2. Architectural Blueprint & Design Patterns

### 2.1 System Architecture Diagram

```
                                    Clients (Web Apps / Mobile iOS & Android / Postman)
                                                           │
                                                           ▼  HTTP (Port 80) / HTTPS (Port 443)
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                            AWS EC2 (34.229.194.135)                                             │
│                                                                                                                 │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                                       Nginx (Alpine Reverse Proxy)                                       │  │
│   │   - Hardened Security Headers (HSTS, X-Content-Type-Options, X-Frame-Options)                            │  │
│   │   - Reverse proxy forwarding to internal Docker network (amrutam-network:8000)                           │  │
│   │   - High performance buffer management & gzip compression                                               │  │
│   └─────────────────────────────────────────────────────┬────────────────────────────────────────────────────┘  │
│                                                         │ Internal Docker Bridge Network                        │
│                                                         ▼                                                       │
│   ┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│   │                                FastAPI Application (Modular Monolith)                                    │  │
│   │   - Middleware: Request ID Correlation, Execution Latency Logger, Security Headers, Rate Limiter        │  │
│   │   - Dependency Injection: Database Session, Redis Connection, Role-Based Access Control Guards          │  │
│   │                                                                                                          │  │
│   │   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────────┐ ┌─────────────────────────┐  │  │
│   │   │     auth      │ │     users     │ │    doctors    │ │  availability  │ │      consultations      │  │  │
│   │   └───────────────┘ └───────────────┘ └───────────────┘ └────────────────┘ └─────────────────────────┘  │  │
│   │   ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌────────────────┐ ┌─────────────────────────┐  │  │
│   │   │ prescriptions │ │   payments    │ │ notifications │ │     audit      │ │ observability (metrics) │  │  │
│   │   └───────────────┘ └───────────────┘ └───────────────┘ └────────────────┘ └─────────────────────────┘  │  │
│   └──────────────────────────┬────────────────────────────────────────────────┬──────────────────────────────┘  │
│                              │                                                │                                 │
│                              │ (Sliding Window & Tasks)                       │ (Asyncpg over TLS)              │
│                              ▼                                                │                                 │
│   ┌───────────────────────────────────────────────────────┐                   │                                 │
│   │                        Redis 7                        │                   │                                 │
│   │   - Sliding-Window Rate Limiting Data Structures      │                   │                                 │
│   │   - Revoked JWT Access Token Blacklist (by JTI)       │                   │                                 │
│   │   - High-throughput ARQ Asynchronous Job Queue        │                   │                                 │
│   └──────────────────────────┬────────────────────────────┘                   │                                 │
│                              │                                                │                                 │
│                              ▼                                                │                                 │
│   ┌───────────────────────────────────────────────────────┐                   │                                 │
│   │                 ARQ Background Worker                 │                   │                                 │
│   │   - Asynchronous Email & SMS Notification Dispatch    │                   │                                 │
│   │   - Cron-based Reconciliation of Orphan Booking Holds │                   │                                 │
│   └───────────────────────────────────────────────────────┘                   │                                 │
└───────────────────────────────────────────────────────────────────────────────┼─────────────────────────────────┘
                                                                                │
                                                                                ▼  Encrypted TLS Connection (Port 5432)
                                                ┌─────────────────────────────────────────────────────────────────┐
                                                │                     AWS RDS PostgreSQL 16                       │
                                                │        database-1.cqly2gic6eyy.us-east-1.rds.amazonaws.com      │
                                                │   - Primary Source of Truth                                     │
                                                │   - Row-Level Locking via SELECT FOR UPDATE                     │
                                                │   - Fully Indexed Relational Tables with Foreign Key Integrity  │
                                                │   - Automated Snapshots, Point-in-Time Recovery                 │
                                                └─────────────────────────────────────────────────────────────────┘
```

### 2.2 Core Architectural Design Patterns

1. **Modular Monolith Architecture**:
   - Each domain feature (Auth, Consultations, Doctors, Prescriptions, Payments) lives in its own dedicated package under `app/modules/`.
   - Each module contains its own `models.py`, `schemas.py`, `service.py`, and `router.py`.
   - Modules communicate via type-annotated services rather than direct cross-boundary database mutations.

2. **Pessimistic Row-Level Locking (`SELECT FOR UPDATE`)**:
   - When a patient books an availability slot, the database row is locked inside an isolated transaction.
   - Any concurrent request attempting to book the same slot is placed on hold until the first transaction commits, guaranteeing that duplicate bookings are physically impossible at the database engine level.

3. **Idempotency Engine**:
   - Critical mutative endpoints (`POST /api/v1/consultations` and `POST /api/v1/consultations/{id}/payments`) enforce the `Idempotency-Key` header.
   - The system checks an `idempotency_keys` table. If the same key is submitted with the exact same request hash, the original stored response is returned without re-executing business logic. If a payload mismatch is detected for the same key, a `422 Unprocessable Entity` is returned.

4. **Transactional Outbox & Asynchronous Worker Pattern**:
   - Heavy tasks (e.g. sending SMS/email confirmations, reconciling expired payments) are decoupled from the HTTP request-response cycle using Redis and ARQ background workers.

---

## 3. Technology Stack & Decision Matrix

| Component / Layer | Technology Selected | Version | Decision Justification |
| :--- | :--- | :--- | :--- |
| **API Framework** | **FastAPI** | `0.110+` | Native async/await support, automatic OpenAPI 3.1 documentation generation, strict Pydantic v2 data validation, and superior throughput. |
| **Language Runtime** | **Python** | `3.12` | Enhanced asyncio performance, improved type hints, and low interpreter overhead. |
| **Async ORM** | **SQLAlchemy** | `2.0.28+` | Declarative 2.0-style queries, explicit async session lifecycle management, robust connection pooling. |
| **Database Driver** | **asyncpg** | `0.29.0+` | Fastest PostgreSQL binary protocol implementation for Python; zero blocking I/O. |
| **Schema Migrations** | **Alembic** | `1.13.1+` | Industry standard version-controlled DDL migrations with automated rollback support. |
| **Caching & Job Queue**| **Redis + ARQ** | `Redis 7` / `ARQ 0.25+` | Microsecond-latency in-memory storage for rate limits, token blacklists, and lightweight job orchestration. |
| **Password Hashing** | **Argon2id** | `argon2-cffi 23.1+` | RFC 9106 recommended memory-hard hashing algorithm, immune to GPU and ASIC brute-force attacks. |
| **Authentication** | **PyJWT / python-jose** | `python-jose 3.3+` | Cryptographically signed JSON Web Tokens (HS256) with custom claims and key identifier (`kid`) rotation. |
| **Multi-Factor Auth** | **PyOTP** | `2.9.0+` | RFC 6238 compliant Time-Based One-Time Password (TOTP) algorithm, compatible with Google Authenticator. |
| **Edge Reverse Proxy** | **Nginx** | `1.25-alpine` | High-performance reverse proxy, connection keep-alives, static documentation pass-through, and SSL termination. |
| **Linting & Code Style**| **Ruff & Mypy** | Latest | Ruff provides 10-100x faster linting and formatting; Mypy enforces strict static type safety. |
| **Security Screening**| **Bandit & Pip-Audit** | Latest | Static AST vulnerability analysis and automated dependency CVE scanning in CI. |
| **Cloud Hosting** | **AWS EC2** | Ubuntu 24.04 LTS | Cloud compute hosting Docker Compose services with automated swap memory allocation. |
| **Managed Database** | **AWS RDS PostgreSQL** | `16.3` | Managed PostgreSQL with automated daily backups, multi-AZ support, and TLS encryption. |

---

## 4. Directory & Modular Layout

```
e:/A_P/
├── app/
│   ├── common/                          # Universal utilities, enums, exceptions & base classes
│   │   ├── constants.py                 # Enums: UserRole, SlotStatus, ConsultationStatus, PaymentStatus
│   │   ├── exceptions.py                # RFC 7807 compliant exception hierarchy & Starlette handlers
│   │   ├── pagination.py                # Paginated query helpers and envelope response models
│   │   └── utils.py                     # Secure UUID generation, timezone-aware UTC datetime helpers
│   ├── core/                            # Cross-cutting foundational infrastructure
│   │   ├── config.py                    # Pydantic v2 BaseSettings loading from environment/.env
│   │   ├── database.py                  # Async engine singleton, sessionmaker, health checks
│   │   ├── dependencies.py              # FastAPI dependencies (RBAC guards, session injection)
│   │   ├── logging.py                   # Structured JSON logger with Correlation-ID tracking
│   │   ├── metrics.py                   # Prometheus latency histograms and HTTP request counters
│   │   ├── middleware.py                # Request correlation ID, latency timing, security headers
│   │   ├── rate_limit.py                # Redis-backed sliding-window rate limiter with fallback
│   │   ├── redis.py                     # Redis client connection pool manager
│   │   ├── security.py                  # Argon2id password hashing, JWT creation/decoding, TOTP
│   │   └── tracing.py                   # OpenTelemetry distributed tracing configuration
│   ├── modules/                         # Cohesive domain feature modules
│   │   ├── audit/                       # Immutable compliance logging and administrative queries
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── auth/                        # User registration, login, token rotation, TOTP MFA
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── availability/                # Doctor schedule slots, batch creation, status patching
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── consultations/               # Pessimistic booking, state machine lifecycle management
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── doctors/                     # Professional doctor directory, search, profile editing
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── notifications/               # Outbox delivery ledger for email and SMS alerts
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   ├── payments/                    # Idempotent payments, mock payment gateway, admin refunds
│   │   │   ├── models.py, schemas.py, service.py, router.py, provider.py
│   │   ├── prescriptions/               # Digital prescription records, dosages, medical notes
│   │   │   ├── models.py, schemas.py, service.py, router.py
│   │   └── users/                       # Patient & doctor profile demographic data
│   │       ├── models.py, schemas.py, service.py, router.py
│   ├── workers/                         # Background task processing
│   │   └── worker.py                    # ARQ background worker functions & cron reconciliation
│   └── main.py                          # Application entry point, router aggregation, lifespan
├── alembic/                             # Database schema migration harness
│   ├── versions/                        # Reversible schema revisions (e.g., 0001_initial_schema.py)
│   ├── env.py                           # Async Alembic runner
│   └── script.py.mako                   # Migration template
├── docker/                              # Container configurations
│   ├── nginx.conf                       # Production Nginx reverse proxy configuration
│   └── prometheus/                      # Prometheus scraper configuration
├── docs/                                # Visual architecture & sequence diagrams
├── scripts/                             # Operational & verification automation
│   └── seed_and_test_all_endpoints.py   # Automated 32-endpoint test & realistic demo data seeder
├── tests/                               # Automated test suite (59 test cases)
│   ├── api/                             # End-to-end integration tests for all 32 endpoints
│   ├── concurrency/                     # Multi-threaded slot booking race condition benchmarks
│   ├── unit/                            # Model, service, and security unit tests
│   └── conftest.py                      # Pytest fixtures and mock database harnesses
├── .github/workflows/
│   └── ci.yml                           # GitHub Actions CI/CD pipeline (Lint, Test, Docker, Deploy)
├── docker-compose.yml                   # Local development topology
├── docker-compose.prod.yml              # Production topology for AWS EC2 & RDS
├── Dockerfile                           # Multi-stage security-hardened non-root container build
├── pyproject.toml                       # Python project configuration (dependencies, Ruff, Mypy)
├── demo_endpoint_report.md              # 100% pass verification audit report
├── demo_endpoint_report.json            # Machine-readable endpoint execution telemetry
└── PROJECT_DOCUMENTATION.md             # Master Engineering Documentation (This file)
```

---

## 5. Database Architecture & Entity Dictionary

The AWS RDS database operates on PostgreSQL 16, utilizing 13 fully normalized tables.

### 5.1 Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    users ||--o| profiles : "has demographic profile"
    users ||--o| doctors : "has clinical profile (if DOCTOR)"
    users ||--o{ refresh_tokens : "owns token families"
    doctors ||--o{ availability_slots : "schedules slots"
    users ||--o{ consultations : "books as patient"
    doctors ||--o{ consultations : "consults as doctor"
    availability_slots ||--o| consultations : "reserved by"
    consultations ||--o{ booking_events : "generates audit events"
    consultations ||--o| prescriptions : "receives prescription"
    consultations ||--o{ payments : "settled by"
    users ||--o{ audit_logs : "actor in"
    users ||--o{ notifications : "recipient of"
```

### 5.2 Complete Entity Dictionary

#### 1. `users`
- **Purpose**: Master authentication identity and credentials table.
- **Fields**:
  - `id` (`UUID`, PK): Unique user identifier.
  - `email` (`VARCHAR(255)`, Unique, Indexed): User email address.
  - `hashed_password` (`VARCHAR(255)`): Argon2id encrypted password hash.
  - `role` (`ENUM`: `PATIENT`, `DOCTOR`, `ADMIN`): System permission role.
  - `is_active` (`BOOLEAN`, Default: `TRUE`): Active account status.
  - `is_mfa_enabled` (`BOOLEAN`, Default: `FALSE`): TOTP MFA activation status.
  - `mfa_secret` (`VARCHAR(255)`, Nullable): Encrypted Base32 TOTP secret.
  - `created_at` (`TIMESTAMPTZ`): UTC creation timestamp.
  - `updated_at` (`TIMESTAMPTZ`): UTC update timestamp.

#### 2. `profiles`
- **Purpose**: Patient demographic and contact information.
- **Fields**:
  - `id` (`UUID`, PK): Profile identifier.
  - `user_id` (`UUID`, FK $\rightarrow$ `users.id`, Unique): Foreign key referencing master user.
  - `first_name` (`VARCHAR(100)`): Given name.
  - `last_name` (`VARCHAR(100)`): Family name.
  - `phone_number` (`VARCHAR(20)`, Nullable): Contact phone number.
  - `date_of_birth` (`DATE`, Nullable): Date of birth.
  - `gender` (`VARCHAR(20)`, Nullable): Gender identification.
  - `address` (`TEXT`, Nullable): Residential address.
  - `created_at`, `updated_at` (`TIMESTAMPTZ`).

#### 3. `doctors`
- **Purpose**: Professional clinical registry and credentials.
- **Fields**:
  - `id` (`UUID`, PK): Doctor identifier.
  - `user_id` (`UUID`, FK $\rightarrow$ `users.id`, Unique): Foreign key referencing master doctor user.
  - `license_number` (`VARCHAR(100)`, Unique, Indexed): Government medical registration number.
  - `specialization` (`VARCHAR(150)`, Indexed): Clinical specialty (e.g., Panchakarma, Kayachikitsa).
  - `experience_years` (`INTEGER`): Years of clinical practice.
  - `consultation_fee` (`NUMERIC(10, 2)`): Standard fee in INR.
  - `bio` (`TEXT`, Nullable): Professional summary and qualifications.
  - `languages` (`ARRAY` / `JSONB`, Nullable): Spoken languages.
  - `is_verified` (`BOOLEAN`, Default: `TRUE`): Credential verification status.
  - `rating` (`NUMERIC(3, 2)`, Default: `5.00`): Patient satisfaction rating.
  - `created_at`, `updated_at` (`TIMESTAMPTZ`).

#### 4. `availability_slots`
- **Purpose**: Bookable time intervals published by doctors.
- **Fields**:
  - `id` (`UUID`, PK): Slot identifier.
  - `doctor_id` (`UUID`, FK $\rightarrow$ `doctors.id`, Indexed): Owning doctor.
  - `start_time` (`TIMESTAMPTZ`, Indexed): Beginning of appointment window.
  - `end_time` (`TIMESTAMPTZ`): End of appointment window.
  - `status` (`ENUM`: `AVAILABLE`, `BOOKED`, `CANCELLED`): Current availability state.
  - `created_at`, `updated_at` (`TIMESTAMPTZ`).
  - **Constraint**: Doctor ID and overlapping time ranges are guarded against collision.

#### 5. `consultations`
- **Purpose**: Central clinical encounter record.
- **Fields**:
  - `id` (`UUID`, PK): Consultation identifier.
  - `patient_id` (`UUID`, FK $\rightarrow$ `users.id`, Indexed): Patient recipient.
  - `doctor_id` (`UUID`, FK $\rightarrow$ `doctors.id`, Indexed): Consulting physician.
  - `availability_slot_id` (`UUID`, FK $\rightarrow$ `availability_slots.id`, Unique): Reserved slot.
  - `status` (`ENUM`: `SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`): State-machine status.
  - `meeting_link` (`VARCHAR(500)`, Nullable): Secure WebRTC / Telehealth room URL.
  - `notes` (`TEXT`, Nullable): Clinical notes.
  - `cancellation_reason` (`TEXT`, Nullable): Reason if cancelled.
  - `created_at`, `updated_at` (`TIMESTAMPTZ`).

#### 6. `booking_events`
- **Purpose**: Append-only event store capturing consultation lifecycle transitions.
- **Fields**:
  - `id` (`UUID`, PK): Event identifier.
  - `consultation_id` (`UUID`, FK $\rightarrow$ `consultations.id`, Indexed): Consultation reference.
  - `event_type` (`VARCHAR(100)`): State transition type (e.g., `CONSULTATION_SCHEDULED`, `PAYMENT_COMPLETED`).
  - `payload` (`JSONB`): Contextual state snapshot at transition.
  - `created_at` (`TIMESTAMPTZ`): UTC event occurrence timestamp.

#### 7. `prescriptions`
- **Purpose**: Legal electronic prescription issued upon encounter completion.
- **Fields**:
  - `id` (`UUID`, PK): Prescription identifier.
  - `consultation_id` (`UUID`, FK $\rightarrow$ `consultations.id`, Unique): Linked consultation.
  - `doctor_id` (`UUID`, FK $\rightarrow$ `doctors.id`): Issuing doctor.
  - `patient_id` (`UUID`, FK $\rightarrow$ `users.id`): Prescribed patient.
  - `diagnosis` (`TEXT`): Clinical diagnosis.
  - `medications` (`JSONB`): Structured medication list (name, dosage, frequency, duration, instructions).
  - `lifestyle_recommendations` (`TEXT`, Nullable): Ayurvedic diet and lifestyle advice (Pathya/Apathya).
  - `follow_up_date` (`DATE`, Nullable): Recommended follow-up review date.
  - `created_at` (`TIMESTAMPTZ`).

#### 8. `payments`
- **Purpose**: Financial transaction ledger for consultations.
- **Fields**:
  - `id` (`UUID`, PK): Payment record identifier.
  - `consultation_id` (`UUID`, FK $\rightarrow$ `consultations.id`, Indexed): Target consultation.
  - `patient_id` (`UUID`, FK $\rightarrow$ `users.id`): Payer.
  - `amount` (`NUMERIC(10, 2)`): Transaction amount in INR.
  - `currency` (`VARCHAR(10)`, Default: `'INR'`): ISO currency code.
  - `status` (`ENUM`: `INITIATED`, `SUCCESS`, `FAILED`, `REFUNDED`): Payment status.
  - `transaction_reference` (`VARCHAR(255)`, Unique): External gateway transaction ID.
  - `idempotency_key` (`VARCHAR(255)`, Unique, Indexed): Client-supplied idempotency key.
  - `refund_reason` (`TEXT`, Nullable): Administrative refund reason if applicable.
  - `created_at`, `updated_at` (`TIMESTAMPTZ`).

#### 9. `idempotency_keys`
- **Purpose**: Mutative request deduplication cache.
- **Fields**:
  - `key` (`VARCHAR(255)`, PK): Unique request idempotency key.
  - `user_id` (`UUID`, FK $\rightarrow$ `users.id`, PK): Owning user identifier.
  - `request_hash` (`VARCHAR(64)`): SHA-256 hash of HTTP method, path, and request body.
  - `response_code` (`INTEGER`): Stored HTTP status code.
  - `response_body` (`JSONB`): Stored JSON response body.
  - `created_at` (`TIMESTAMPTZ`).

#### 10. `refresh_tokens`
- **Purpose**: Refresh token family rotation with automatic theft detection.
- **Fields**:
  - `id` (`UUID`, PK): Token record identifier.
  - `user_id` (`UUID`, FK $\rightarrow$ `users.id`, Indexed): Owning user.
  - `token_hash` (`VARCHAR(64)`, Unique, Indexed): SHA-256 hash of the issued refresh token.
  - `family_id` (`UUID`, Indexed): Token family identifier.
  - `is_revoked` (`BOOLEAN`, Default: `FALSE`): Revocation flag.
  - `expires_at` (`TIMESTAMPTZ`): Expiration timestamp.
  - `created_at` (`TIMESTAMPTZ`).

#### 11. `notifications`
- **Purpose**: Message dispatch queue and delivery ledger.
- **Fields**:
  - `id` (`UUID`, PK): Notification identifier.
  - `recipient_id` (`UUID`, FK $\rightarrow$ `users.id`, Indexed): Message recipient.
  - `channel` (`ENUM`: `EMAIL`, `SMS`, `IN_APP`): Delivery channel.
  - `title` (`VARCHAR(255)`): Subject or notification heading.
  - `content` (`TEXT`): Full notification message body.
  - `status` (`ENUM`: `QUEUED`, `DELIVERED`, `FAILED`): Dispatch status.
  - `created_at`, `delivered_at` (`TIMESTAMPTZ`).

#### 12. `audit_logs`
- **Purpose**: Tamper-evident compliance trail for clinical and administrative actions.
- **Fields**:
  - `id` (`UUID`, PK): Log entry identifier.
  - `actor_id` (`UUID`, FK $\rightarrow$ `users.id`, Nullable, Indexed): User performing the action.
  - `action` (`VARCHAR(100)`, Indexed): Operation performed (e.g., `PRESCRIPTION_CREATED`, `PAYMENT_REFUNDED`).
  - `resource_type` (`VARCHAR(100)`, Indexed): Entity modified (e.g., `Consultation`, `Payment`).
  - `resource_id` (`VARCHAR(255)`, Indexed): Entity primary key.
  - `ip_address` (`VARCHAR(45)`, Nullable): Client IP address.
  - `user_agent` (`TEXT`, Nullable): Client HTTP user agent.
  - `details` (`JSONB`, Nullable): Diff or structured event metadata.
  - `created_at` (`TIMESTAMPTZ`, Indexed).

#### 13. `alembic_version`
- **Purpose**: Tracks active Alembic schema revision (`version_num VARCHAR(32)`).

---

## 6. Security, Cryptography & Compliance

### 6.1 Authentication Lifecycle

```
Client (User)                               FastAPI Auth Router                         Redis / Database
     │                                               │                                         │
     │ 1. POST /api/v1/auth/login                    │                                         │
     ├──────────────────────────────────────────────>│                                         │
     │    {email, password}                          │ 2. Verify Argon2id Hash                 │
     │                                               ├────────────────────────────────────────>│
     │                                               │    Hash valid, MFA enabled?             │
     │                                               │                                         │
     │    [Case A: MFA Not Enabled]                  │ 3. Generate Access Token (15 min)       │
     │ <─────────────────────────────────────────────┤    Generate Refresh Token (7 days)      │
     │    {access_token, refresh_token}              │    Store hashed token family            │
     │                                               ├────────────────────────────────────────>│
     │                                               │                                         │
     │    [Case B: MFA Enabled]                      │                                         │
     │ <─────────────────────────────────────────────┤ 4. Return Temporary MFA Challenge Token │
     │    {mfa_required: true, mfa_token: "..."}     │                                         │
     │                                               │                                         │
     │ 5. POST /api/v1/auth/mfa/verify               │                                         │
     ├──────────────────────────────────────────────>│                                         │
     │    {mfa_token, totp_code: "123456"}           │ 6. Verify RFC 6238 TOTP with Base32     │
     │                                               │    Issue Access + Refresh Token         │
     │ <─────────────────────────────────────────────┴─────────────────────────────────────────┤
     │    {access_token, refresh_token}                                                        │
```

### 6.2 Refresh Token Rotation & Family Theft Detection
- When a refresh token is exchanged at `/api/v1/auth/token/refresh`, the submitted token is **immediately revoked**.
- A new refresh token is generated within the same `family_id`.
- **Theft Detection Mechanism**: If an attacker attempts to replay an already-revoked refresh token, the system recognizes a token reuse anomaly, **immediately invalidates all tokens in that family**, and forces all active sessions for that user to terminate.

### 6.3 Rate Limiting & Denial of Service Protection
- Redis-backed sliding-window rate limiting prevents credential brute-forcing and API flooding:
  - **Login attempts**: 5 requests / minute per IP.
  - **Consultation booking**: 20 requests / minute per user.
  - **General read endpoints**: 100 requests / minute per client.
- When quotas are exceeded, the API returns `HTTP 429 Too Many Requests` with a `Retry-After` header.

### 6.4 Role-Based Access Control (RBAC) & IDOR Protection
- Endpoints enforce granular role checks via FastAPI dependency injection:
  - `require_role(UserRole.PATIENT)`
  - `require_role(UserRole.DOCTOR)`
  - `require_role(UserRole.ADMIN)`
- Insecure Direct Object References (IDOR) are prevented: Patients can only view their own consultations, prescriptions, and payment records. Doctors can only manage their own slots and patients assigned to them.

---

## 7. Deterministic State Machines & Concurrency Controls

### 7.1 Consultation Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> SCHEDULED : Patient books slot (SELECT FOR UPDATE)
    SCHEDULED --> CONFIRMED : Payment successfully captured
    CONFIRMED --> IN_PROGRESS : Doctor starts consultation
    IN_PROGRESS --> COMPLETED : Consultation concluded (Prescription issued)
    SCHEDULED --> CANCELLED : Patient/Doctor cancels before start
    CONFIRMED --> CANCELLED : Cancelled with refund trigger
    COMPLETED --> [*]
    CANCELLED --> [*]
```

- **Invariant**: Once marked `COMPLETED`, a consultation cannot be modified or cancelled.
- **Invariant**: Prescriptions can only be issued by the assigned doctor for consultations in `IN_PROGRESS` or `COMPLETED` states.

### 7.2 Concurrency Race Benchmark
- **Problem**: In high-demand scenarios, multiple patients may attempt to book the same doctor availability slot at the same millisecond.
- **Solution**: The booking service executes `SELECT ... FOR UPDATE` on the target slot row within an isolated database transaction.
- **Validation Result**: Under an automated benchmark of **100 concurrent asynchronous requests**:
  - **1 request succeeded (`201 Created`)**.
  - **99 requests were rejected (`409 Conflict - SLOT_ALREADY_BOOKED`)**.
  - **0 duplicate records** were created.

---

## 8. Background Workers & Asynchronous Task Processing

The background worker runs as a dedicated non-blocking ARQ process connected to Redis:

### 8.1 Registered Worker Functions

1. **`send_notification_job(ctx, notification_id)`**:
   - Asynchronously loads notification from the database.
   - Dispatches message to downstream provider (AWS SES / Twilio / Firebase).
   - Marks status as `DELIVERED` or records failure with exponential backoff retries.

2. **`reconcile_stuck_payments_job(ctx)` (Cron Job)**:
   - Runs periodically every 5 minutes.
   - Queries `payments` where `status = INITIATED` older than 5 minutes.
   - Marks abandoned transactions as `FAILED` and emits a `PAYMENT_RECONCILIATION_FAILED` booking event to release unconfirmed slots.

---

## 9. Complete API Reference (All 32 Endpoints with Payloads)

### 9.1 Observability & Health (3 Endpoints)

#### 1. `GET /health`
- **Auth**: None
- **Response `200 OK`**:
```json
{
  "status": "ok",
  "environment": "production"
}
```

#### 2. `GET /ready`
- **Auth**: None
- **Response `200 OK`**:
```json
{
  "status": "ready",
  "database": "connected",
  "redis": "connected"
}
```

#### 3. `GET /metrics`
- **Auth**: None
- **Description**: Exposes Prometheus exposition format metrics (HTTP request counts, latency histograms, system memory).

---

### 9.2 Authentication & MFA (6 Endpoints)

#### 4. `POST /api/v1/auth/register`
- **Auth**: None
- **Request Body**:
```json
{
  "email": "patient.aarav@amrutam.com",
  "password": "SecurePassword@123",
  "role": "PATIENT",
  "first_name": "Aarav",
  "last_name": "Patel",
  "phone_number": "+919876543210"
}
```
- **Response `201 Created`**:
```json
{
  "id": "c1f72780-e8f3-4f9e-a8df-755d918bb13b",
  "email": "patient.aarav@amrutam.com",
  "role": "PATIENT",
  "is_active": true,
  "is_mfa_enabled": false,
  "created_at": "2026-09-19T04:22:10.123456Z"
}
```

#### 5. `POST /api/v1/auth/login`
- **Auth**: None
- **Request Body**:
```json
{
  "email": "patient.aarav@amrutam.com",
  "password": "SecurePassword@123"
}
```
- **Response `200 OK`**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIntpZCI6InYxIn0...",
  "refresh_token": "d8e3b4a2f1c0...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### 6. `POST /api/v1/auth/mfa/enroll`
- **Auth**: Bearer Token
- **Response `200 OK`**:
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/Amrutam%20Telemedicine:patient.aarav@amrutam.com?secret=JBSWY3DPEHPK3PXP&issuer=Amrutam%20Telemedicine"
}
```

#### 7. `POST /api/v1/auth/mfa/verify`
- **Auth**: None (Uses `mfa_token` from challenge)
- **Request Body**:
```json
{
  "mfa_token": "temporary_challenge_jwt",
  "code": "584920"
}
```
- **Response `200 OK`**: Returns valid `access_token` and `refresh_token`.

#### 8. `POST /api/v1/auth/token/refresh`
- **Auth**: None
- **Request Body**:
```json
{
  "refresh_token": "d8e3b4a2f1c0..."
}
```
- **Response `200 OK`**: Returns rotated token pair.

#### 9. `POST /api/v1/auth/logout`
- **Auth**: Bearer Token
- **Request Body**:
```json
{
  "refresh_token": "d8e3b4a2f1c0..."
}
```
- **Response `200 OK`**:
```json
{
  "detail": "Successfully logged out"
}
```

---

### 9.3 User Profiles (2 Endpoints)

#### 10. `GET /api/v1/users/me`
- **Auth**: Bearer Token
- **Response `200 OK`**:
```json
{
  "id": "c1f72780-e8f3-4f9e-a8df-755d918bb13b",
  "email": "patient.aarav@amrutam.com",
  "role": "PATIENT",
  "first_name": "Aarav",
  "last_name": "Patel",
  "phone_number": "+919876543210",
  "date_of_birth": "1994-06-15",
  "gender": "MALE",
  "address": "42 Vasant Kunj, New Delhi"
}
```

#### 11. `PATCH /api/v1/users/me`
- **Auth**: Bearer Token
- **Request Body**:
```json
{
  "phone_number": "+919999888877",
  "address": "77 Indiranagar, Bengaluru"
}
```
- **Response `200 OK`**: Returns updated profile object.

---

### 9.4 Doctor Directory (4 Endpoints)

#### 12. `GET /api/v1/doctors`
- **Auth**: None
- **Query Params**: `specialization=Panchakarma&min_rating=4.5&page=1&size=10`
- **Response `200 OK`**:
```json
{
  "items": [
    {
      "id": "d4e21a00-1122-3344-5566-778899aabbcc",
      "name": "Dr. Rajesh Sharma",
      "specialization": "Ayurvedic Medicine & Panchakarma",
      "experience_years": 14,
      "consultation_fee": 850.00,
      "rating": 4.95,
      "languages": ["English", "Hindi", "Sanskrit"]
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

#### 13. `GET /api/v1/doctors/{doctor_id}`
- **Auth**: None
- **Response `200 OK`**: Full doctor credential profile including bio and verification status.

#### 14. `POST /api/v1/doctors/me`
- **Auth**: Bearer Token (Doctor Role)
- **Request Body**:
```json
{
  "license_number": "AYUSH-DL-2015-8942",
  "specialization": "Kayachikitsa & Herbal Pharmacology",
  "experience_years": 10,
  "consultation_fee": 600.00,
  "bio": "Specialist in chronic metabolic disorders and rasayana therapy.",
  "languages": ["English", "Hindi"]
}
```
- **Response `201 Created`**: Returns initialized doctor record.

#### 15. `PATCH /api/v1/doctors/me`
- **Auth**: Bearer Token (Doctor Role)
- **Request Body**:
```json
{
  "consultation_fee": 750.00,
  "bio": "Updated clinical summary."
}
```
- **Response `200 OK`**: Returns updated doctor profile.

---

### 9.5 Availability Scheduling (4 Endpoints)

#### 16. `POST /api/v1/doctors/me/availability`
- **Auth**: Bearer Token (Doctor Role)
- **Request Body**:
```json
{
  "slots": [
    {
      "start_time": "2026-09-20T10:00:00Z",
      "end_time": "2026-09-20T10:45:00Z"
    },
    {
      "start_time": "2026-09-20T11:00:00Z",
      "end_time": "2026-09-20T11:45:00Z"
    }
  ]
}
```
- **Response `201 Created`**: Returns array of created slot objects with status `AVAILABLE`.

#### 17. `GET /api/v1/doctors/{doctor_id}/availability`
- **Auth**: None
- **Query Params**: `from_date=2026-09-20T00:00:00Z&to_date=2026-09-21T00:00:00Z`
- **Response `200 OK`**: Array of bookable slots for the target doctor.

#### 18. `PATCH /api/v1/availability/{slot_id}`
- **Auth**: Bearer Token (Doctor Role)
- **Request Body**:
```json
{
  "status": "CANCELLED"
}
```
- **Response `200 OK`**: Returns modified slot object.

#### 19. `DELETE /api/v1/availability/{slot_id}`
- **Auth**: Bearer Token (Doctor Role)
- **Response `204 No Content`**: Deletes unbooked slot.

---

### 9.6 Consultations Lifecycle (6 Endpoints)

#### 20. `POST /api/v1/consultations`
- **Auth**: Bearer Token (Patient Role)
- **Headers**: `Idempotency-Key: f3c1e2a0-4b68-4f11-9a7c-333333333333`
- **Request Body**:
```json
{
  "availability_slot_id": "b0a1c2d3-e4f5-6789-0123-456789abcdef",
  "notes": "Experiencing chronic indigestion and fatigue for 3 weeks."
}
```
- **Response `201 Created`**:
```json
{
  "id": "e5b6a7c8-d9e0-1234-5678-9abcdef01234",
  "patient_id": "c1f72780-e8f3-4f9e-a8df-755d918bb13b",
  "doctor_id": "d4e21a00-1122-3344-5566-778899aabbcc",
  "availability_slot_id": "b0a1c2d3-e4f5-6789-0123-456789abcdef",
  "status": "SCHEDULED",
  "meeting_link": "https://telehealth.amrutam.co.in/room/e5b6a7c8",
  "created_at": "2026-09-19T04:25:00Z"
}
```

#### 21. `GET /api/v1/consultations`
- **Auth**: Bearer Token
- **Query Params**: `status=SCHEDULED&page=1&size=10`
- **Response `200 OK`**: Paginated list of consultations scoped to the caller.

#### 22. `GET /api/v1/consultations/{id}`
- **Auth**: Bearer Token
- **Response `200 OK`**: Full details of consultation, meeting link, and doctor/patient info.

#### 23. `POST /api/v1/consultations/{id}/start`
- **Auth**: Bearer Token (Doctor Role)
- **Response `200 OK`**: Transitions status to `IN_PROGRESS`.

#### 24. `POST /api/v1/consultations/{id}/complete`
- **Auth**: Bearer Token (Doctor Role)
- **Response `200 OK`**: Transitions status to `COMPLETED`.

#### 25. `POST /api/v1/consultations/{id}/cancel`
- **Auth**: Bearer Token (Patient or Doctor)
- **Request Body**:
```json
{
  "cancellation_reason": "Patient requested reschedule due to emergency travel."
}
```
- **Response `200 OK`**: Cancels consultation and restores slot status to `AVAILABLE`.

---

### 9.7 Clinical Prescriptions (3 Endpoints)

#### 26. `POST /api/v1/consultations/{id}/prescriptions`
- **Auth**: Bearer Token (Doctor Role)
- **Request Body**:
```json
{
  "diagnosis": "Mandagni (Impaired Digestive Fire) and Vata-Pitta Imbalance",
  "medications": [
    {
      "name": "Amrutam Kuntal Care Herbal Syrup",
      "dosage": "15 ml",
      "frequency": "Twice daily after meals",
      "duration": "30 days",
      "instructions": "Mix with equal parts lukewarm water"
    },
    {
      "name": "Triphala Churna",
      "dosage": "5 grams",
      "frequency": "Once daily at bedtime",
      "duration": "14 days",
      "instructions": "Take with warm cow milk"
    }
  ],
  "lifestyle_recommendations": "Avoid heavy, oily, and processed foods. Follow Ushnodaka (lukewarm water) regimen. Practice 15 minutes of Pranayama daily.",
  "follow_up_date": "2026-10-19"
}
```
- **Response `201 Created`**:
```json
{
  "id": "a9b8c7d6-e5f4-3210-fedc-ba9876543210",
  "consultation_id": "e5b6a7c8-d9e0-1234-5678-9abcdef01234",
  "diagnosis": "Mandagni (Impaired Digestive Fire) and Vata-Pitta Imbalance",
  "medications": [ ... ],
  "created_at": "2026-09-19T04:26:00Z"
}
```

#### 27. `GET /api/v1/consultations/{id}/prescriptions`
- **Auth**: Bearer Token
- **Response `200 OK`**: Retrieves prescription associated with the consultation ID.

#### 28. `GET /api/v1/prescriptions/{id}`
- **Auth**: Bearer Token
- **Response `200 OK`**: Retrieves digital prescription by its primary key ID.

---

### 9.8 Payments & Refunds (3 Endpoints)

#### 29. `POST /api/v1/consultations/{id}/payments`
- **Auth**: Bearer Token (Patient Role)
- **Headers**: `Idempotency-Key: p7a8b9c0-1234-5678-90ab-cdef12345678`
- **Request Body**:
```json
{
  "amount": 850.00,
  "currency": "INR",
  "payment_method": "UPI",
  "simulate_failure": false
}
```
- **Response `200 OK`**:
```json
{
  "id": "7b8c9d0e-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
  "consultation_id": "e5b6a7c8-d9e0-1234-5678-9abcdef01234",
  "amount": 850.00,
  "currency": "INR",
  "status": "SUCCESS",
  "transaction_reference": "TXN_AMRUTAM_MOCK_992147",
  "created_at": "2026-09-19T04:25:30Z"
}
```

#### 30. `GET /api/v1/consultations/{id}/payments`
- **Auth**: Bearer Token
- **Response `200 OK`**: List of payment attempts for the consultation.

#### 31. `POST /api/v1/payments/{id}/refund`
- **Auth**: Bearer Token (Admin Role)
- **Request Body**:
```json
{
  "reason": "Doctor could not attend scheduled consultation due to medical emergency."
}
```
- **Response `200 OK`**:
```json
{
  "id": "7b8c9d0e-1a2b-3c4d-5e6f-7a8b9c0d1e2f",
  "status": "REFUNDED",
  "refund_reason": "Doctor could not attend scheduled consultation due to medical emergency.",
  "updated_at": "2026-09-19T04:27:00Z"
}
```

---

### 9.9 Audit & Compliance (1 Endpoint)

#### 32. `GET /api/v1/audit/logs`
- **Auth**: Bearer Token (Admin Role)
- **Query Params**: `action=PRESCRIPTION_CREATED&page=1&size=20`
- **Response `200 OK`**:
```json
{
  "items": [
    {
      "id": "01920000-0000-7000-8000-000000000001",
      "actor_id": "d4e21a00-1122-3344-5566-778899aabbcc",
      "action": "PRESCRIPTION_CREATED",
      "resource_type": "Prescription",
      "resource_id": "a9b8c7d6-e5f4-3210-fedc-ba9876543210",
      "ip_address": "172.31.26.0",
      "created_at": "2026-09-19T04:26:01Z"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 20
}
```

---

## 10. Error Handling & RFC 7807 Problem Details Catalog

The platform strictly implements RFC 7807 problem details specification. All errors adhere to this JSON contract:

```json
{
  "type": "https://amrutam.co.in/errors/slot_already_booked",
  "title": "Conflict",
  "status": 409,
  "detail": "The requested availability slot is no longer available.",
  "instance": "/api/v1/consultations",
  "error_code": "SLOT_ALREADY_BOOKED"
}
```

### Standard Error Code Registry

| HTTP Status | Error Code | Description / Trigger Condition |
| :--- | :--- | :--- |
| `400 Bad Request` | `BAD_REQUEST` | Malformed parameters, invalid query values, or date range violations. |
| `401 Unauthorized` | `UNAUTHORIZED` | Expired, tampered, missing JWT Bearer token, or blacklisted token. |
| `401 Unauthorized` | `MFA_REQUIRED` | Valid password provided, but TOTP MFA verification is mandatory. |
| `403 Forbidden` | `FORBIDDEN` | Insufficient RBAC role permissions or attempting to access another user's clinical record. |
| `404 Not Found` | `RESOURCE_NOT_FOUND` | Primary key ID does not exist in the database. |
| `409 Conflict` | `SLOT_ALREADY_BOOKED` | Availability slot has already been reserved by another patient. |
| `409 Conflict` | `INVALID_STATUS_TRANSITION`| Attempting to execute an illegal state machine jump (e.g. canceling completed consultation). |
| `422 Unprocessable`| `IDEMPOTENCY_PAYLOAD_MISMATCH`| Same `Idempotency-Key` resubmitted with conflicting request body parameters. |
| `429 Too Many Req` | `RATE_LIMIT_EXCEEDED` | Exceeded sliding-window quota; client must honor `Retry-After` seconds. |
| `500 Internal Error`| `INTERNAL_SERVER_ERROR`| Unhandled server exception (logged with Correlation-ID). |
| `503 Unavailable` | `SERVICE_UNAVAILABLE` | Database connection pool exhaustion or critical downstream outage. |

---

## 11. Environment Configuration Dictionary

All configuration is managed through Pydantic v2 `BaseSettings` (`app/core/config.py`), reading from the environment or `.env` file:

| Variable Name | Type | Default Value | Production AWS Setting | Description |
| :--- | :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `str` | `development` | `production` | Deployment mode (`development`, `testing`, `production`). |
| `APP_NAME` | `str` | `Amrutam Telemedicine Backend` | `Amrutam Telemedicine Backend` | Name exposed in OpenAPI schemas and health responses. |
| `API_V1_PREFIX` | `str` | `/api/v1` | `/api/v1` | Global URL prefix for feature routers. |
| `LOG_LEVEL` | `str` | `INFO` | `INFO` | Logging threshold (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `SECRET_KEY` | `str` | (Dev insecure key) | (Cryptographic secret) | Master cryptographic seed key (minimum 32 characters). |
| `JWT_SECRET_KEY` | `str` | (Dev insecure key) | (Cryptographic secret) | HMAC secret for signing and verifying JWT tokens. |
| `JWT_ALGORITHM` | `str` | `HS256` | `HS256` | Cryptographic algorithm for JWT tokens. |
| `JWT_KID` | `str` | `v1` | `v1` | Key identifier used for seamless JWT rotation. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `int` | `15` | `15` | Expiration window for access tokens (15 minutes). |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `int` | `7` | `7` | Expiration window for refresh tokens (7 days). |
| `DATABASE_URL` | `str` | `postgresql+asyncpg://...` | `postgresql+asyncpg://postgres:PASSWORD@database-1...rds.amazonaws.com:5432/postgres?ssl=require` | Async PostgreSQL database connection URI with TLS enforcement. |
| `DB_POOL_SIZE` | `int` | `20` | `10` (for t2.micro) | Size of SQLAlchemy persistent connection pool. |
| `DB_MAX_OVERFLOW` | `int` | `10` | `5` | Maximum temporary connections above pool size. |
| `DB_POOL_TIMEOUT` | `int` | `30` | `30` | Seconds to wait before timing out on pool checkout. |
| `REDIS_URL` | `str` | `redis://localhost:6379/0` | `redis://redis:6379/0` | Redis connection URI for rate limiting and ARQ. |
| `RATE_LIMIT_LOGIN_PER_MIN` | `int` | `5` | `5` | Maximum login attempts allowed per minute. |
| `RATE_LIMIT_CONSULTATION_PER_MIN`| `int` | `20` | `20` | Maximum consultation bookings allowed per minute. |
| `RATE_LIMIT_GENERAL_PER_MIN`| `int` | `100` | `100` | Maximum general HTTP requests allowed per minute. |
| `CORS_ORIGINS` | `list` | `["http://localhost:3000"]` | `*` or domain list | Allowed CORS origins (comma-delimited string in `.env`). |
| `PROMETHEUS_METRICS_ENABLED` | `bool` | `True` | `True` | Whether to expose Prometheus metrics at `/metrics`. |

---

## 12. Testing, Quality Assurance & Concurrency Benchmark

The platform is fortified with **59 automated tests** providing **>80% test coverage**:

```bash
# Execute local test suite with full coverage reporting
pytest --cov=app --cov-report=term-missing tests/
```

### 12.1 Test Suite Organization
1. **API Integration Tests (`tests/api/`)**: Exercises all 32 HTTP routes against mock database engines to verify request validation, status codes, and serialization.
2. **Service Unit Tests (`tests/unit/`)**: Validates business invariants, state machine transitions, and error handling.
3. **Security Unit Tests (`tests/unit/test_security.py`)**: Tests Argon2id cost parameters, JWT expiration, token revocation blacklists, and TOTP generation.
4. **Concurrency Race Condition Tests (`tests/concurrency/`)**: Simulates 100 simultaneous requests contending for a single availability slot.

### 12.2 Verification Report Summary

| Verification Stage | Metric / Command | Result | Status |
| :--- | :--- | :--- | :--- |
| **All 32 Endpoints Verification** | `scripts/seed_and_test_all_endpoints.py` | **32 / 32 Passed (100%)** | 🟢 PASS |
| **Code Formatting** | `ruff format --check .` | Clean | 🟢 PASS |
| **Code Linting** | `ruff check .` | 0 errors | 🟢 PASS |
| **Strict Type Checking** | `mypy app/ --ignore-missing-imports` | Success: no issues found | 🟢 PASS |
| **Security AST Audit** | `bandit -r app/ -ll -ii` | 0 high/medium vulnerabilities | 🟢 PASS |
| **Dependency Vulnerability Scan**| `pip-audit` | 0 known CVEs | 🟢 PASS |

---

## 13. DevOps, Cloud Infrastructure & CI/CD Pipeline

### 13.1 AWS Cloud Topology

- **AWS Region**: `us-east-1` (North Virginia)
- **AWS EC2 Compute**:
  - **Public IPv4**: `34.229.194.135`
  - **Operating System**: Ubuntu 24.04 LTS
  - **Memory Configuration**: 1 GiB Physical RAM + **2 GiB Virtual Swap** (avoids OOM kills during Docker image builds)
  - **Docker Containers**:
    - `amrutam-nginx` (Nginx 1.25-alpine on port 80/443)
    - `amrutam-api` (FastAPI Uvicorn on internal port 8000)
    - `amrutam-worker` (ARQ background worker)
    - `amrutam-redis` (Redis 7 in-memory cache)
- **AWS RDS Managed Database**:
  - **Endpoint**: `database-1.cqly2gic6eyy.us-east-1.rds.amazonaws.com:5432`
  - **Engine**: PostgreSQL 16.3
  - **Security Group**: Inbound port 5432 allowed for EC2 public IP; TLS enforced.

### 13.2 Continuous Delivery Architecture (`.github/workflows/ci.yml`)

The CI/CD pipeline triggers on any pull request or push to `main`:

```
git push origin main
       │
       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Job 1: Lint, Test & Build                             │
│   ├── Step 1: Check out code & set up Python 3.12                               │
│   ├── Step 2: Install dependencies & system libpq-dev                           │
│   ├── Step 3: Run Ruff Code Formatter check (`ruff format --check .`)           │
│   ├── Step 4: Run Ruff Linter (`ruff check .`)                                  │
│   ├── Step 5: Run Mypy Type Analysis (`mypy app/ --ignore-missing-imports`)      │
│   ├── Step 6: Run Bandit Security Analysis (`bandit -r app/ -ll -ii`)           │
│   ├── Step 7: Scan Dependencies for CVEs (`pip-audit`)                          │
│   ├── Step 8: Execute Pytest Suite with Coverage (`pytest --cov=app`)           │
│   ├── Step 9: Build Production Docker Image (`docker build`)                    │
│   └── Step 10: Scan Image for Vulnerabilities (`trivy-action`)                  │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         ▼ (Triggered on 'main' branch if Job 1 passes)
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Job 2: Deploy to AWS EC2                              │
│   ├── Step 1: Connect via SSH using GitHub Repository Secret (`EC2_SSH_KEY`)    │
│   ├── Step 2: Pull latest code on server (`git pull origin main`)               │
│   ├── Step 3: Build & start containers (`docker compose up -d --build`)         │
│   ├── Step 4: Run Database Migrations (`alembic upgrade head`)                  │
│   └── Step 5: Prune obsolete images (`docker image prune -f`)                   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 14. Step-by-Step GitHub Actions Setup Guide

To enable automated continuous deployments on your repository, configure these **3 GitHub Repository Secrets**:

### Step 1: Open GitHub Repository Settings
1. Go to your GitHub repository: `https://github.com/GauravVishwa5/A_P`
2. Click **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
3. Click **New repository secret**.

### Step 2: Add Required Secrets

1. **`EC2_HOST`**:
   - Value: `34.229.194.135`
2. **`EC2_USER`**:
   - Value: `ubuntu`
3. **`EC2_SSH_KEY`**:
   - Value: Paste the complete private key content (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`) of the key authorized to SSH into the EC2 instance.

Once added, every push to `main` will automatically test the application, build the containers, deploy them to EC2, run database migrations, and verify system health!

---

## 15. Postman Automated Collection & Pre-Seeded Demo Data

### 15.1 Pre-Seeded Accounts in AWS RDS

Your production database is pre-loaded with verified demo records:

| Role | Full Name | Email Address | Password | Pre-Configured State |
| :--- | :--- | :--- | :--- | :--- |
| **ADMIN** | Administrator | `admin@amrutam.com` | `AmrutamAdmin@2026!` | Global audit logs, refund processing |
| **DOCTOR** | Dr. Rajesh Sharma | `dr.sharma@amrutam.com` | `DoctorPassword@123` | Ayurvedic & Panchakarma specialist (Fee: ₹850, 4 Slots) |
| **DOCTOR** | Dr. Ananya Iyer | `dr.ananya@amrutam.com` | `DoctorPassword@123` | Kayachikitsa specialist (Fee: ₹600, 3 Slots) |
| **PATIENT** | Aarav Patel | `patient.aarav@amrutam.com` | `PatientPassword@123` | Active & completed consultations, prescription, paid invoice |
| **PATIENT** | Priya Sen | `patient.priya@amrutam.com` | `PatientPassword@123` | Demonstrates consultation cancellation flow |

### 15.2 Postman Automated Collection File
- **Collection File**: [`amrutam-telemedicine.postman_collection.json`](file:///e:/A_P/amrutam-telemedicine.postman_collection.json)
- **Features**:
  - **Automatic Token Capture**: Authenticating stores `access_token` and `refresh_token` automatically in collection variables.
  - **Dynamic Entity Propagation**: Doctor IDs, Slot IDs, Consultation IDs, Prescription IDs, and Payment IDs automatically chain from creation requests to downstream actions.

---

## 16. Operations, Runbook & Maintenance Guide

### 16.1 Server Management Commands (SSH into EC2)

```bash
# Navigate to application root
cd /home/ubuntu/amrutam-backend

# Check container health status
docker compose -f docker-compose.prod.yml ps

# View live streaming logs across all services
docker compose -f docker-compose.prod.yml logs -f

# View live logs for a specific service
docker compose -f docker-compose.prod.yml logs -f api
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f worker

# Restart all containers
docker compose -f docker-compose.prod.yml restart

# Rebuild containers after manual code edits
docker compose -f docker-compose.prod.yml up -d --build
```

### 16.2 Database Migrations & Seeding

```bash
# Run pending database migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Rollback last migration revision
docker compose -f docker-compose.prod.yml exec api alembic downgrade -1

# Re-run full endpoint verification test & demo seeder against RDS
docker compose -f docker-compose.prod.yml exec api python scripts/seed_and_test_all_endpoints.py
```

### 16.3 Troubleshooting & Common Fixes

1. **Swagger UI Shows Blank Page**:
   - **Cause**: Content Security Policy (CSP) blocking external CDN scripts (`cdn.jsdelivr.net`).
   - **Fix**: Verify `SecurityHeadersMiddleware` in `app/core/middleware.py` bypasses CSP on `/docs`, `/redoc`, and `/openapi.json`.
2. **Nginx Returns 502 Bad Gateway**:
   - **Cause**: Nginx cached an outdated Docker container internal IP during a container rebuild.
   - **Fix**: Restart Nginx: `docker compose -f docker-compose.prod.yml restart nginx`.
3. **Database Connection Timeout**:
   - **Cause**: AWS RDS security group blocked inbound port 5432 or public access disabled.
   - **Fix**: Ensure the RDS Security Group allows TCP port 5432 from the EC2 instance public IP (`34.229.194.135`).

---

> **Amrutam Telemedicine Backend** — Built with architectural rigor, defensive concurrency, and clinical security.
