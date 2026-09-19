# 📊 Amrutam Telemedicine Platform - Comprehensive API Endpoint Verification Report

> **Generated:** 2026-09-19 04:25:49 UTC  
> **Test Execution Environment:** Localhost (PostgreSQL `amrutam_db`)  
> **Total Endpoints Tested:** 32 / 32  
> **Pass Rate:** **32 / 32 (100.0%)**  
> **Average Latency:** **2183.5 ms**

## 1. Demo User Accounts & Credentials Seeded

| Role | Name | Email | Password | Key Associated Entities |
| :--- | :--- | :--- | :--- | :--- |
| **ADMIN** | System Administrator | `admin@amrutam.com` | `AmrutamAdmin@2026!` | Audit logs, Refund authority |
| **DOCTOR** | Dr. Rajesh Sharma | `dr.sharma@amrutam.com` | `DoctorPassword@123` | Specialization: Ayurvedic Medicine, Panchakarma (Fee: ₹850) |
| **DOCTOR** | Dr. Ananya Iyer | `dr.ananya@amrutam.com` | `DoctorPassword@123` | Specialization: Kayachikitsa, Herbal Pharmacology (Fee: ₹600) |
| **PATIENT** | Aarav Patel | `patient.aarav@amrutam.com` | `PatientPassword@123` | Active consultation, Settled payment, Digital prescription |
| **PATIENT** | Priya Sen | `patient.priya@amrutam.com` | `PatientPassword@123` | Cancelled consultation demonstration |

---

## 2. All 32 Endpoints Test Results

| # | Method | Endpoint Path | Category | Status Code | Latency | Result | Key Details / Payload |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `GET` | `/health` | System | `200` (Exp: `200`) | 16.76 ms | ✅ PASS | {'status': 'ok'} |
| 2 | `GET` | `/ready` | System | `200` (Exp: `200`) | 1656.12 ms | ✅ PASS | {'status': 'ready', 'database': True, 'redis': True} |
| 3 | `GET` | `/metrics` | System | `200` (Exp: `200`) | 2.77 ms | ✅ PASS | 4999 bytes telemetry |
| 4 | `POST` | `/api/v1/auth/register` | Authentication | `201` (Exp: `201`) | 2772.55 ms | ✅ PASS | Registered test.user.e86cc9@amrutam.com (ID: a96b1cab-e399-4e2f-90b7-7c26c4d60463) |
| 5 | `POST` | `/api/v1/auth/login` | Authentication | `200` (Exp: `200`) | 1739.42 ms | ✅ PASS | Issued JWT bearer token (exp: 900s) |
| 6 | `POST` | `/api/v1/auth/mfa/enroll` | Authentication | `200` (Exp: `200`) | 1866.13 ms | ✅ PASS | Generated Base32 secret: 2LSRZV... |
| 7 | `POST` | `/api/v1/auth/mfa/verify` | Authentication | `200` (Exp: `200`) | 1454.31 ms | ✅ PASS | Verified 6-digit TOTP code and issued full token pair |
| 8 | `POST` | `/api/v1/auth/token/refresh` | Authentication | `200` (Exp: `200`) | 2294.25 ms | ✅ PASS | Rotated refresh token with single-use family theft protection |
| 9 | `POST` | `/api/v1/auth/logout` | Authentication | `204` (Exp: `204`) | 1456.14 ms | ✅ PASS | Revoked access and refresh tokens |
| 10 | `GET` | `/api/v1/users/me` | Users | `200` (Exp: `200`) | 1451.77 ms | ✅ PASS | Retrieved profile for Aarav Patel |
| 11 | `PATCH` | `/api/v1/users/me` | Users | `200` (Exp: `200`) | 3305.78 ms | ✅ PASS | Updated phone: +919876543299 |
| 12 | `GET` | `/api/v1/doctors` | Doctors | `200` (Exp: `200`) | 1458.01 ms | ✅ PASS | Found 2 registered doctors |
| 13 | `GET` | `/api/v1/doctors/{doctor_id}` | Doctors | `200` (Exp: `200`) | 1240.5 ms | ✅ PASS | Dr. Specialization: Ayurvedic Medicine & Panchakarma, Fee: ₹850.00 |
| 14 | `POST` | `/api/v1/doctors/me` | Doctors | `201` (Exp: `201`) | 2908.59 ms | ✅ PASS | Created profile (Doctor ID: b89e7f89-aa22-4422-9044-6b292fd79e38) |
| 15 | `PATCH` | `/api/v1/doctors/me` | Doctors | `200` (Exp: `200`) | 3109.01 ms | ✅ PASS | Updated fee to ₹800.00, exp: 11 yrs |
| 16 | `POST` | `/api/v1/doctors/me/availability` | Availability | `201` (Exp: `201`) | 4159.91 ms | ✅ PASS | Created 2 schedule slots |
| 17 | `GET` | `/api/v1/doctors/{doctor_id}/availability` | Availability | `200` (Exp: `200`) | 1448.95 ms | ✅ PASS | Found 5 available slots for Dr. Sharma |
| 18 | `PATCH` | `/api/v1/availability/{slot_id}` | Availability | `200` (Exp: `200`) | 3322.72 ms | ✅ PASS | Updated slot status to CANCELLED |
| 19 | `DELETE` | `/api/v1/availability/{slot_id}` | Availability | `204` (Exp: `204`) | 2490.57 ms | ✅ PASS | Deleted unbooked slot 9a750ba0-d187-4172-91c6-a142f0c30777 |
| 20 | `POST` | `/api/v1/consultations` | Consultations | `201` (Exp: `201`) | 3572.32 ms | ✅ PASS | Consultation booked: 0572fb41-0ea1-4770-9342-b81b3467315e (Status: SCHEDULED) |
| 21 | `GET` | `/api/v1/consultations` | Consultations | `200` (Exp: `200`) | 2073.83 ms | ✅ PASS | Caller has 1 consultations |
| 22 | `GET` | `/api/v1/consultations/{consultation_id}` | Consultations | `200` (Exp: `200`) | 1654.06 ms | ✅ PASS | Meeting Ref: None |
| 23 | `POST` | `/api/v1/consultations/{consultation_id}/start` | Consultations | `200` (Exp: `200`) | 2286.34 ms | ✅ PASS | Status updated to: IN_PROGRESS |
| 24 | `POST` | `/api/v1/consultations/{consultation_id}/complete` | Consultations | `200` (Exp: `200`) | 2284.44 ms | ✅ PASS | Status updated to: COMPLETED |
| 25 | `POST` | `/api/v1/consultations/{consultation_id}/cancel` | Consultations | `200` (Exp: `200`) | 2499.38 ms | ✅ PASS | Consultation cancelled. Reason: Schedule clash due to unavoidable business travel. |
| 26 | `POST` | `/api/v1/consultations/{consultation_id}/prescriptions` | Prescriptions | `201` (Exp: `201`) | 2509.19 ms | ✅ PASS | Prescription ID: 072c6ef4-0fca-488e-ace9-058001cde508 (3 medications prescribed) |
| 27 | `GET` | `/api/v1/consultations/{consultation_id}/prescriptions` | Prescriptions | `200` (Exp: `200`) | 1447.65 ms | ✅ PASS | Diagnosis: Vata-Pitta Dushti manifesting as Agnimandya (... |
| 28 | `GET` | `/api/v1/prescriptions/{prescription_id}` | Prescriptions | `200` (Exp: `200`) | 1652.62 ms | ✅ PASS | Prescribed to Patient ID: 428736bf-319a-411a-80a8-22de8755cbfd |
| 29 | `POST` | `/api/v1/consultations/{consultation_id}/payments` | Payments | `201` (Exp: `201`) | 4437.9 ms | ✅ PASS | Payment ID: 6e992d70-949d-440e-b92a-5bad37711e9b (Status: SUCCESS, Amount: ₹600.00) |
| 30 | `GET` | `/api/v1/consultations/{consultation_id}/payments` | Payments | `200` (Exp: `200`) | 1862.23 ms | ✅ PASS | Retrieved 1 payment records |
| 31 | `POST` | `/api/v1/payments/{payment_id}/refund` | Payments | `200` (Exp: `200`) | 3340.39 ms | ✅ PASS | Refund processed. Status: REFUNDED |
| 32 | `GET` | `/api/v1/audit/logs` | Audit & Compliance | `200` (Exp: `200`) | 2097.45 ms | ✅ PASS | Retrieved 0 immutable compliance records |

---

## 3. Postman & Swagger Interactive Testing Instructions

1. **Start Local Backend Server:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. **Open Interactive Swagger UI:**
   - Navigate to [http://localhost:8000/docs](http://localhost:8000/docs)
3. **Import Postman Collection:**
   - Import [`amrutam-telemedicine.postman_collection.json`](amrutam-telemedicine.postman_collection.json)
   - Execute **Auth > Login** with any of the demo accounts above.
   - The collection script will automatically capture the access & refresh token and inject them into subsequent requests!
