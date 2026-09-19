# Production Security Controls Checklist

A comprehensive audit checklist verifying security controls implemented across the codebase.

## 1. Authentication & Session Management
- [x] **Password Storage**: Argon2id with recommended OWASP parameters (time cost 3, memory 64MB, parallelism 4).
- [x] **JWT Cryptography**: Signed with `HS256`, explicit `kid="v1"` header, and expiration enforcement.
- [x] **JTI Blocklisting**: Revoked tokens stored in Redis with remaining TTL for instant logout invalidation.
- [x] **Refresh Token Rotation**: One-time use tokens with automated cryptographic family revocation on token reuse.
- [x] **Multi-Factor Authentication**: RFC 6238 TOTP with Base32 secret generation, QR provisioning URI, and single-use time windows.

## 2. Authorization & Data Isolation (IDOR)
- [x] **UUIDv4 Identifiers**: All resources use non-enumerable UUIDv4 primary keys.
- [x] **RBAC Enforcement**: FastAPI dependencies restrict endpoints by user roles (`PATIENT`, `DOCTOR`, `ADMIN`).
- [x] **IDOR Protection**:
  - Patients can only retrieve their own profiles, consultations, and prescriptions.
  - Doctors can only view consultations and issue prescriptions for consultations assigned to them.
  - Foreign access attempts return HTTP 403 Forbidden.

## 3. Data Integrity & Concurrency
- [x] **Pessimistic Slot Locking**: `SELECT ... FOR UPDATE` prevents simultaneous booking interleaving.
- [x] **Database-Level Invariant**: Partial unique index (`uq_consultations_slot_active`) prevents double bookings.
- [x] **Doctor Slot Overlap Protection**: Enforced via application-level transactional interval query validation (`check_overlap`) combined with database-level composite unique constraint on `(doctor_id, start_time)` and active consultation barrier index (`uq_consultations_slot_active`).
- [x] **Idempotency Keys**: Clients send `Idempotency-Key` header with SHA-256 hash payload verification.

## 4. API & Network Security
- [x] **Security Headers Middleware**: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin`, `Content-Security-Policy`.
- [x] **Rate Limiting**: Distributed Redis sliding window counter per client IP.
- [x] **Input Validation**: Strict Pydantic models with `extra="forbid"` preventing mass-assignment attacks.
- [x] **Log Redaction**: Sensitive fields (`password`, `token`, `authorization`, `secret`, `credit_card`) automatically sanitized from structured logs.
