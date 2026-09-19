# Database Entity-Relationship (ER) Diagram

The Amrutam Telemedicine schema comprises 12 normalized relational tables designed for strict ACID semantics and complete auditability.

```mermaid
erDiagram
    users ||--o| profiles : has
    users ||--o| doctors : "registers as"
    users ||--o{ refresh_tokens : owns
    users ||--o{ notifications : receives
    users ||--o{ audit_logs : generates

    doctors ||--o{ availability_slots : schedules
    doctors ||--o{ consultations : conducts
    doctors ||--o{ prescriptions : writes

    users ||--o{ consultations : books
    availability_slots ||--o| consultations : reserves

    consultations ||--o| prescriptions : "concludes with"
    consultations ||--o{ payments : incurs
    consultations ||--o{ booking_events : logs

    users {
        UUID id PK
        string email UK
        string password_hash
        string role
        boolean is_active
        boolean is_verified
        boolean mfa_enabled
        string mfa_secret
        timestamp created_at
        timestamp updated_at
    }

    profiles {
        UUID id PK
        UUID user_id FK,UK
        string full_name
        string phone_number
        date date_of_birth
        string gender
        text address
    }

    doctors {
        UUID id PK
        UUID user_id FK,UK
        string license_number UK
        string specialization
        integer experience_years
        decimal consultation_fee
        text bio
        string_array languages
        decimal rating
        integer total_reviews
        boolean is_available
    }

    availability_slots {
        UUID id PK
        UUID doctor_id FK
        timestamp start_time
        timestamp end_time
        string status
        tstzrange slot_range
    }

    consultations {
        UUID id PK
        UUID patient_id FK
        UUID doctor_id FK
        UUID availability_slot_id FK
        string status
        timestamp scheduled_start
        timestamp scheduled_end
        text reason
        text cancellation_reason
    }

    prescriptions {
        UUID id PK
        UUID consultation_id FK,UK
        UUID doctor_id FK
        UUID patient_id FK
        text diagnosis
        jsonb medications
        text notes
        timestamp created_at
    }

    payments {
        UUID id PK
        UUID consultation_id FK
        UUID patient_id FK
        decimal amount
        string currency
        string status
        string provider
        string transaction_reference
        string idempotency_key UK
    }

    refresh_tokens {
        UUID id PK
        UUID user_id FK
        string token_hash UK
        UUID family_id
        boolean is_revoked
        timestamp expires_at
    }

    idempotency_keys {
        UUID id PK
        string idempotency_key UK
        string request_hash
        jsonb response_payload
        integer status_code
        timestamp expires_at
    }

    booking_events {
        UUID id PK
        UUID consultation_id FK
        string event_type
        jsonb payload
        timestamp created_at
    }

    notifications {
        UUID id PK
        UUID recipient_id FK
        string type
        string channel
        string title
        text body
        string status
        timestamp sent_at
    }

    audit_logs {
        UUID id PK
        UUID actor_id
        string actor_role
        string action
        string resource_type
        string resource_id
        string status
        jsonb metadata
        timestamp created_at
    }
```

## Key Database Constraints

1. `uq_consultations_slot_active`: Partial unique index guaranteeing only one active consultation (`SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`) can exist per `availability_slot_id`.
2. `uq_prescriptions_consultation`: Unique 1-to-1 constraint preventing multiple prescriptions per consultation.
3. `uq_payments_idempotency_key`: Unique constraint preventing duplicate charges for the same client request key.
4. `uq_doctor_slot_time`: Database composite unique constraint on `(doctor_id, start_time)` combined with application-level transactional range validation (`check_overlap`) preventing overlapping availability intervals.
