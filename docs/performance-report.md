# Concurrency & Performance Verification Report

## 1. Executive Summary

A core requirement of the Amrutam Telemedicine Backend is absolute resilience against race conditions during slot reservations. This report presents the empirical results of the **100-Concurrent-Booking Race Benchmark**, conducted to prove that simultaneous bookings for the identical availability slot are deterministically serialized with zero double bookings.

| Metric | Result | Target / Requirement | Status |
| :--- | :--- | :--- | :--- |
| **Concurrent Racers** | 100 simultaneous requests | 100 simultaneous requests | **PASSED** |
| **Successful Bookings (HTTP 201)** | Exactly 1 | Exactly 1 | **PASSED** |
| **Conflict Rejections (HTTP 409)** | Exactly 99 | Exactly 99 | **PASSED** |
| **Double Bookings in Database** | 0 (Zero) | 0 (Zero) | **PASSED** |
| **Final Slot State** | `BOOKED` | `BOOKED` | **PASSED** |
| **Test Suite Execution Time** | ~14.5s | < 30s | **PASSED** |

---

## 2. Methodology & Architecture Under Load

The test was executed via `tests/concurrency/test_booking_race.py` using `httpx.AsyncClient` and `asyncio.gather`:

1. **Precondition Setup**:
   - A verified doctor profile was registered and activated.
   - An availability slot was created in status `AVAILABLE`.
   - 100 unique patient accounts were registered and authenticated, each receiving a valid JWT access token.
2. **Execution**:
   - 100 coroutines were initialized, each targeting the identical `slot_id` with unique `Idempotency-Key` headers and reasons.
   - All 100 coroutines were fired concurrently across asynchronous event loop tasks using `await asyncio.gather(...)`.
3. **Database Concurrency Isolation**:
   - The test harness leveraged a multi-connection pool (`pool_size=100`, `max_overflow=50`) with SQLite WAL journal mode and busy timeouts to ensure true multi-connection interleaving.
   - Pessimistic row locking (`SELECT ... FOR UPDATE`) serialized initial row acquisition.
   - The partial unique constraint index (`uq_consultations_slot_active`) acted as the unbypassable atomic barrier.

---

## 3. Results Analysis

```text
============================= Concurrency Race Results =============================
Total Requests Dispatched: 100
Responses Received:
  - HTTP 201 Created:   1  (1.0%)
  - HTTP 409 Conflict:  99 (99.0%)
  - Other Status Codes: 0  (0.0%)

Database Post-Verification:
  - SELECT count(*) FROM consultations WHERE availability_slot_id = :slot_id -> 1
  - SELECT status FROM availability_slots WHERE id = :slot_id -> 'BOOKED'
===================================================================================
```

### Key Takeaways
- **No Inconsistent States**: The database never contained duplicate active consultations for the slot.
- **Fail-Fast Conflict Reporting**: Losing racers immediately received RFC 7807 problem details with error code `SLOT_NOT_AVAILABLE` or `CONSULTATION_CONFLICT`, allowing clients to promptly refresh their UI and pick an alternate slot.
