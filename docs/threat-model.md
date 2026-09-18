# Security Architecture & Threat Model (STRIDE)

This document delineates the threat modeling analysis, mitigated attack vectors, and architectural controls implemented across the Amrutam Telemedicine platform.

## 1. STRIDE Threat Analysis

| Threat Category | Potential Attack Vector | Implemented Architectural Mitigation |
| :--- | :--- | :--- |
| **Spoofing Identity** | Attacker impersonates doctor or patient via stolen JWT or credentials. | • Argon2id password hashing with high memory cost ($64\text{MB}$).<br>• Short-lived access tokens ($15\text{ mins}$) signed with `HS256` and active `kid="v1"`.<br>• TOTP MFA (PyOTP RFC 6238) with single-use verification windows.<br>• Refresh token rotation with immediate cryptographic family revocation upon replay. |
| **Tampering with Data** | Attacker alters prescription details or modifies medical records in transit. | • TLS termination at Nginx proxy with strict HSTS.<br>• Prescriptions are 100% immutable once issued (no PUT/PATCH endpoints exposed).<br>• Cryptographic request payload hashing (SHA-256) for idempotency validation. |
| **Repudiation** | Doctor denies issuing a prescription; patient denies requesting consultation. | • Append-only `audit_logs` table recording actor ID, IP, User-Agent, and timestamps.<br>• `booking_events` ledger tracking state machine transitions. |
| **Information Disclosure** | IDOR: Patient reads another patient's medical history or prescription via sequential ID enumeration. | • Random UUIDv4 used exclusively for all public identifiers (zero integer sequences).<br>• Granular IDOR access control checks in every service method validating `current_user.id == resource.patient_id` or assigned doctor.<br>• Log redaction engine masking passwords, tokens, and authorization headers in JSON logs. |
| **Denial of Service** | Botnet spams login or reservation endpoints to exhaust database connections. | • Distributed sliding-window rate limiter backed by Redis sorted sets (10 req/min on auth, 60 req/min on standard endpoints).<br>• Pessimistic row locking timeouts (`busy_timeout` / lock acquisition limits) preventing cascading worker exhaustion. |
| **Elevation of Privilege** | Normal patient submits doctor availability or triggers administrative refund. | • Role-Based Access Control (RBAC) enforced via FastAPI dependency injection (`require_roles(...)`).<br>• Profile verification requirement for doctor-restricted endpoints. |

---

## 2. In-Depth Defensive Controls

### Authentication & Refresh Token Rotation Family Theft Detection
When a client presents a refresh token:
1. The token hash is looked up in `refresh_tokens`.
2. If `is_revoked == True`, an attacker is attempting to reuse an invalidated token.
3. The system immediately revokes **all** refresh tokens belonging to that `family_id` and emits a high-priority security audit event: `REFRESH_TOKEN_THEFT_DETECTED`.

### Prescriptions Immutability & Clinical Authorization
1. Prescriptions can **only** be issued if `consultation.status` is `IN_PROGRESS` or `COMPLETED`.
2. Only the specific doctor assigned to the consultation can issue the prescription (`consultation.doctor_id == doctor.id`).
3. Once created, no update or delete endpoints exist. Database constraints enforce a strict 1-to-1 relationship.
