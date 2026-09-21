# Initial Domain Model

This is a specification for later phases, not a claim that all tables or workflows exist in Phase 0.

## Entities

| Entity | Ownership and purpose |
| --- | --- |
| `Company` | Tenant root. Every business record belongs to exactly one company. |
| `User` | Authenticated identity with one or more scoped roles; includes owner/admin, supervisor, or driver capability. |
| `Driver` | Company-scoped operational profile linked to a user identity. |
| `Supervisor` | Company-scoped operational profile linked to a user identity. |
| `Site` | Company-owned/permitted work location. |
| `Tipper` | Company-owned tipper asset. Rented and non-tipper equipment are out of V1 scope. |
| `Assignment` | Effective-dated driver + tipper + site + supervisor relationship. Historical events keep this reference. |
| `Device` | Registered mobile device/session metadata used for event provenance and sync diagnostics. |
| `TripEvent` | Immutable-ish driver event identified by client event UUID, assignment, device time, server receive time, sync state, and verification state. |
| `KmReading` | START or END odometer submission with reading value and supporting photo reference. Conflicts and missing pairs become explicit exceptions. |
| `DieselEvent` | DIESEL_ISSUED / DIESEL_RECORDED event with litres and supporting photo. It is not fuel consumption. |
| `EmergencyEvent` | BREAKDOWN, ACCIDENT, TYRE_OR_VEHICLE_PROBLEM, or CONTACT_SUPERVISOR event with timestamps and lifecycle status. |
| `Verification` | Actor, decision, time, reason, and target event/version for supervisor review. |
| `AuditLog` | Append-only record of actor, company, action, target, time, old value, new value, reason, and request ID. |

## Relationships

```text
Company
├── Users ── Driver / Supervisor profiles
├── Sites
├── owned Tippers
├── Assignments ── Driver + Tipper + Site + Supervisor
├── Devices
└── operational events ──> one historical Assignment
                         ├── TripEvent
                         ├── KmReading
                         ├── DieselEvent
                         └── EmergencyEvent
```

## Invariants

1. A business record cannot be read across companies, even if a caller guesses its UUID.
2. An active assignment is determined by effective timestamps and company scope; driver/tipper permanence is forbidden.
3. Event UUID is unique within the backend event namespace and repeated sync is idempotent.
4. Separate event UUIDs remain separate records even when timestamps are close. A possible duplicate is a review signal, never silent deletion.
5. Device-created and server-received timestamps are both retained and interpreted as UTC.
6. Sync state and verification state are separate state machines.
7. KM readings never silently overwrite conflicts. End below start, missing pair, and conflicting readings are explicit exceptions.
8. Diesel issued is not fuel consumed and must not produce same-day km/litre by default.
9. Approved history cannot be silently overwritten. Amendments and audit records preserve who, when, reason, old value, and new value.
10. Supporting uploads are validated for size and MIME type, sanitized, and stored through the S3-compatible abstraction.

