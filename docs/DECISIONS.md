# Architecture Decisions & Assumptions Log

Running log of every architectural decision and every assumption made where the PRD
or build instructions were ambiguous. Newest entries appended at the bottom of each
milestone section.

---

## M1 — Skeleton & tenancy (2026-06-10)

### D-001 · PRD location
Instructions reference `docs/PRD.md`; the file existed at the repo root as
`PRD-UAE-eInvoicing-SaaS.md`. Moved it to `docs/PRD.md` (content unchanged).

### D-002 · Repo was not a git repository
The working directory contained no `.git`. Initialized a fresh repository with
`main` as the default branch.

### D-003 · Sync SQLAlchemy + psycopg 3
Chose synchronous SQLAlchemy sessions (psycopg 3 driver) over async. Rationale:
Celery workers (M4) are sync, the RLS GUC pattern is simpler with one transaction
per request, and FastAPI's threadpool comfortably covers MVP load (NFR: dashboard
< 2s p95). Revisit only if load testing says so.

### D-004 · Membership is M:N from day one
PRD FR-1.4 requires the Accountant role to be linked across multiple tenants, so
`User` is a global identity and `TenantMembership(user_id, tenant_id, role)` carries
the role per tenant. JWT access tokens embed the *active* tenant + role; switching
tenants issues new tokens (`POST /auth/switch-tenant`).

### D-005 · RLS mechanics
- App connects as `fawtara_app` (NOSUPERUSER, NOBYPASSRLS), created in migration
  0001 with a dev password. **Production must override this role's password /
  manage it via the secrets vault** — tracked for the pre-launch security pass.
- Policies key on transaction-local GUCs `app.current_tenant_id` and
  `app.current_user_id` (set with `set_config(..., is_local => true)`).
- `ENABLE` + `FORCE ROW LEVEL SECURITY` on: `tenants`, `tenant_memberships`,
  `refresh_tokens`, `otp_codes` — and every business table added later.
- Pre-tenant-selection flows (login, list-my-tenants, refresh) use the *user* GUC
  arm of the policies. No RLS-bypass role is used anywhere in the app.

### D-006 · `users` table is NOT under RLS
`users` is global identity infrastructure (no `tenant_id` — accountants span
tenants), and login must look up a user by email before any context exists.
Isolation for user *data* is enforced where it is tenant-owned (memberships).
"Every business table has tenant_id + RLS" applies to tenant-owned business data;
`users` is the documented exception.

### D-007 · Tenant-isolation test scope in M1
The required "tenant A can never read tenant B's invoices" test can only fully land
with the invoice table (M2/M3). M1 proves the identical mechanism on
`tenants`/`tenant_memberships` at the SQL level (RLS) and the repository level, and
the invoice test will be added the moment the invoices table exists. Tracked.

### D-008 · Google sign-in deferred (PRD conflict)
PRD FR-1.1 lists Google sign-in; the build instructions fix auth scope to
email+password JWT + OTP stub. **Instructions win** → Google OAuth deferred to a
later phase. Flagged per working agreement.

### D-009 · Signup issues tokens before phone verification
PRD FR-1.1 mandates WhatsApp OTP verification. With OTP being a stub in MVP, signup
returns tokens immediately and `users.phone_verified` stays `false` until
`POST /auth/otp/verify`. The onboarding checklist (M6) surfaces it, and invoice
*transmission* can later be gated on it if the real OTP lands before launch.

### D-010 · Error envelope shape
Standardized now (so M2 reuses it):
`{"errors": [{code, field, message_en, message_ar, suggestion_en, suggestion_ar}]}`.
The instructions' shape had a single `suggestion`; split into `_en`/`_ar` for
bilingual parity with messages. All texts come from `backend/locales/{en,ar}.json`.

### D-011 · Pydantic request validation vs domain validation
FastAPI request-shape errors (missing field, bad email) are mapped into the
bilingual envelope with catalog texts for known codes and a generic bilingual
message otherwise. The *invoice* domain (M2) will not rely on pydantic messages —
it gets a dedicated rule engine with per-rule bilingual texts, per instructions.

### D-012 · Compose host ports
Host ports 5433 (Postgres) and 6380 (Redis) to avoid colliding with locally
installed services. In-network ports remain standard (5432/6379). CI uses 5432.

### D-013 · TRN immutable after signup
`PATCH /tenants/me` deliberately excludes `trn`: changing the tax registration
number silently is compliance-sensitive. A support/admin flow (FR-9, admin console)
will own TRN corrections.

### D-014 · Deferred M1 niceties (tracked, not forgotten)
- Rate limiting on auth endpoints (NFR) → security pass, week 7–8.
- Member removal / role change endpoints → with settings screens (M6) at latest.
- Frontend compose service → M6 (compose currently runs db, redis, api, worker).
- TOTP 2FA (NFR "optional") → post-MVP.

### D-015 · Role permission matrix (M1 scope)
| Action | OWNER | ACCOUNTANT | STAFF | READONLY |
|---|---|---|---|---|
| Read tenant profile / members / own user | ✓ | ✓ | ✓ | ✓ (profile+self only) |
| Update tenant profile | ✓ | — | — | — |
| Add members | ✓ | — | — | — |
| List members | ✓ | ✓ | — | — |

Later milestones extend this matrix (invoices: STAFF can create/edit, READONLY view).
