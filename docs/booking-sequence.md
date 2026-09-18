# Consultation Booking & State Machine Sequence

## 1. Booking Sequence with Idempotency & Pessimistic Locking

The diagram below illustrates the exact runtime message flow when a patient books an available slot with race protection and idempotency checking.

```mermaid
sequenceDiagram
    autonumber
    actor Patient
    participant API as FastAPI Service
    participant IdemRepo as Idempotency Engine
    participant DB as PostgreSQL (ACID)
    participant Redis as Redis (Events/Queue)

    Patient->>+API: POST /api/v1/consultations (Idempotency-Key, slot_id)
    
    API->>IdemRepo: Check Idempotency Key & SHA-256 Hash
    alt Key exists with matching hash
        IdemRepo-->>API: Return Cached ConsultationResponse
        API-->>Patient: 201 Created (Cached)
    else Key exists with mismatched hash
        API-->>Patient: 422 Unprocessable Content (IDEMPOTENCY_PAYLOAD_MISMATCH)
    end

    API->>+DB: BEGIN TRANSACTION
    API->>DB: SELECT * FROM availability_slots WHERE id = :slot_id FOR UPDATE
    
    alt Slot status != 'AVAILABLE'
        DB-->>API: Slot Status == 'BOOKED'
        API->>DB: ROLLBACK
        API-->>Patient: 409 Conflict (SLOT_NOT_AVAILABLE)
    end

    API->>DB: UPDATE availability_slots SET status = 'BOOKED' WHERE id = :slot_id
    API->>DB: INSERT INTO consultations (patient_id, doctor_id, slot_id, status='SCHEDULED')
    
    alt Unique Constraint Collision (uq_consultations_slot_active)
        DB-->>API: IntegrityError (Violates partial unique index)
        API->>DB: ROLLBACK
        API-->>Patient: 409 Conflict (SLOT_NOT_AVAILABLE)
    else Success
        API->>DB: INSERT INTO idempotency_keys (key, hash, response)
        API->>DB: INSERT INTO booking_events (type='BOOKING_INITIATED')
        API->>DB: COMMIT TRANSACTION
        DB-->>-API: Transaction Committed
        API-)Redis: Enqueue Async Booking Notification
        API-->>-Patient: 201 Created (Consultation Details)
    end
```

---

## 2. Consultation Lifecycle State Machine

Consultations progress strictly through explicit, auditable status transitions.

```mermaid
stateDiagram-v2
    [*] --> SCHEDULED: Patient Books Slot (Locked)
    
    SCHEDULED --> CONFIRMED: Payment Captured (SUCCESS)
    SCHEDULED --> CANCELLED: Patient or Doctor Cancels (Slot Released -> AVAILABLE)
    
    CONFIRMED --> IN_PROGRESS: Doctor Starts Consultation (Doctor Only)
    CONFIRMED --> CANCELLED: Patient / Admin Cancels (Slot Released -> AVAILABLE)
    
    IN_PROGRESS --> COMPLETED: Doctor Completes Consultation (Doctor Only)
    
    COMPLETED --> [*]: Immutable Prescription Issued
    CANCELLED --> [*]: Finalized Audit Record
```

### Transition Invariants Table

| Initial State | Target State | Permitted Actor | Side Effects |
| :--- | :--- | :--- | :--- |
| `SCHEDULED` | `CONFIRMED` | System / Patient | Payment recorded as `SUCCESS`; booking event emitted. |
| `SCHEDULED` | `CANCELLED` | Patient / Doctor / Admin | Associated `availability_slot` reset to `AVAILABLE`. |
| `CONFIRMED` | `IN_PROGRESS`| Assigned Doctor | Consultation started; clinical timer initiates. |
| `CONFIRMED` | `CANCELLED` | Patient / Admin | Slot released; refund initiated if applicable. |
| `IN_PROGRESS`| `COMPLETED`  | Assigned Doctor | Consultation closed; enables prescription issuance. |
| `COMPLETED`  | Any          | *None* | Terminal state. Prescriptions issued are 100% immutable. |
