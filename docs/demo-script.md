# API Walkthrough & Demonstration Script

A step-by-step terminal script for evaluators to test the complete Amrutam Telemedicine API flow using `curl` or Postman.

## Pre-requisite
Ensure the server is running locally:
```bash
docker compose up -d
# or via virtual environment:
uvicorn app.main:app --reload --port 8000
```
Base URL: `http://localhost:8000`

### 🚀 Postman Collection Quickstart (Zero-Manual Auth)
An automated Postman collection is provided in `docs/amrutam-telemedicine.postman_collection.json` (and at the repository root):
1. **Import**: Open Postman -> click **Import** -> select `amrutam-telemedicine.postman_collection.json`.
2. **Auto-Auth on Register / Login**:
   - Send `1. Authentication -> Register Patient` or `Register Doctor`. The embedded Postman test script registers the account and automatically logs in, saving `access_token` and `refresh_token` into collection variables.
   - Or send `1. Authentication -> Login`. The test script immediately saves `access_token` and `refresh_token`.
3. **Automatic Bearer Authentication**: All subsequent requests (`Users`, `Doctors`, `Consultations`, `Prescriptions`, `Payments`) inherit `Authorization: Bearer {{access_token}}` from collection settings. No manual copying needed!
4. **Auto-Captured IDs**: Whenever you create a doctor profile, create availability slots, book a consultation, or issue a prescription, their respective IDs (`doctor_id`, `slot_id`, `consultation_id`, `prescription_id`, `payment_id`) are auto-saved to collection variables.

---

## 1. Register and Onboard Doctor

### Step 1.1: Register Doctor Account
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dr.sharma@amrutam.co.in",
    "password": "Password123!",
    "role": "DOCTOR"
  }'
```

### Step 1.2: Log in Doctor
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "dr.sharma@amrutam.co.in",
    "password": "Password123!"
  }'
# Copy access_token as DOCTOR_TOKEN
```

### Step 1.3: Create Doctor Profile
```bash
curl -X POST http://localhost:8000/api/v1/doctors/me \
  -H "Authorization: Bearer $DOCTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "license_number": "AYUSH-DL-2024-9988",
    "specialization": "Kayachikitsa",
    "experience_years": 12,
    "consultation_fee": "750.00",
    "bio": "Senior Ayurvedic Practitioner specializing in chronic stress management.",
    "languages": ["English", "Hindi", "Sanskrit"]
  }'
# Save returned "id" as DOCTOR_ID
```

### Step 1.4: Publish Availability Slots
```bash
curl -X POST http://localhost:8000/api/v1/doctors/me/availability \
  -H "Authorization: Bearer $DOCTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "slots": [
      {
        "start_time": "2026-10-01T10:00:00Z",
        "end_time": "2026-10-01T10:30:00Z"
      }
    ]
  }'
# Save returned slot "id" as SLOT_ID
```

---

## 2. Patient Registration & Consultation Booking

### Step 2.1: Register Patient
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patient.verma@example.com",
    "password": "Password123!",
    "role": "PATIENT"
  }'
```

### Step 2.2: Log in Patient
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patient.verma@example.com",
    "password": "Password123!"
  }'
# Copy access_token as PATIENT_TOKEN
```

### Step 2.3: Search Available Doctors
```bash
curl -X GET "http://localhost:8000/api/v1/doctors?specialization=Kayachikitsa" \
  -H "Authorization: Bearer $PATIENT_TOKEN"
```

### Step 2.4: Book Consultation (Idempotent)
```bash
curl -X POST http://localhost:8000/api/v1/consultations \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -H "Idempotency-Key: demo-key-10001" \
  -H "Content-Type: application/json" \
  -d "{
    \"doctor_id\": \"$DOCTOR_ID\",
    \"slot_id\": \"$SLOT_ID\",
    \"reason\": \"Chronic insomnia and anxiety\"
  }"
# Save returned "id" as CONSULTATION_ID
```

---

## 3. Payment Processing

### Step 3.1: Process Consultation Payment
```bash
curl -X POST "http://localhost:8000/api/v1/consultations/$CONSULTATION_ID/payments" \
  -H "Authorization: Bearer $PATIENT_TOKEN" \
  -H "Idempotency-Key: pay-key-8899" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "750.00",
    "currency": "INR",
    "mock_mode": "SUCCESS"
  }'
```

---

## 4. Consultation Lifecycle & Prescription

### Step 4.1: Doctor Starts Consultation
```bash
curl -X POST "http://localhost:8000/api/v1/consultations/$CONSULTATION_ID/start" \
  -H "Authorization: Bearer $DOCTOR_TOKEN"
```

### Step 4.2: Doctor Completes Consultation
```bash
curl -X POST "http://localhost:8000/api/v1/consultations/$CONSULTATION_ID/complete" \
  -H "Authorization: Bearer $DOCTOR_TOKEN"
```

### Step 4.3: Doctor Issues Immutable Prescription
```bash
curl -X POST "http://localhost:8000/api/v1/consultations/$CONSULTATION_ID/prescriptions" \
  -H "Authorization: Bearer $DOCTOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "diagnosis": "Vata imbalance causing sleep disturbance",
    "notes": "Follow Sattvic warm diet; practice Pranayama nightly",
    "medications": [
      {
        "name": "Ashwagandha Tablet",
        "dosage": "500mg",
        "frequency": "Twice daily with warm milk",
        "duration": "30 days",
        "instructions": "Take after dinner"
      }
    ]
  }'
```

### Step 4.4: Patient Retrieves Prescription
```bash
curl -X GET "http://localhost:8000/api/v1/consultations/$CONSULTATION_ID/prescriptions" \
  -H "Authorization: Bearer $PATIENT_TOKEN"
```

---

## 5. Observability & Health Probes

```bash
# Liveness Probe
curl -X GET http://localhost:8000/health

# Readiness Probe (Checks PostgreSQL and Redis connections)
curl -X GET http://localhost:8000/ready

# Prometheus Metrics Telemetry
curl -X GET http://localhost:8000/metrics
```
