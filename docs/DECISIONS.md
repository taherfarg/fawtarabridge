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

---

## M2 — Canonical model & PINT-AE engine (2026-06-10)

### D-016 · Vendored OASIS UBL 2.1 XSDs as a structural self-check
The official PINT-AE XSD/Schematron is not yet in hand, so the engine validates
its own output against the vendored OASIS UBL 2.1 Invoice schema
(`backend/assets/xsd/ubl-2.1/`, 14 files, downloaded from docs.oasis-open.org).
This catches serializer structure/ordering bugs; the PINT-AE Schematron slots in
beside it once published. Business correctness lives in the Python rule layer.

### D-017 · VAT category and rate are structurally required
`InvoiceLine.vat_category` / `vat_rate` have no defaults: defaulting tax treatment
would be guessing. Everything else in `CanonicalInvoice` is structurally permissive
(empty strings, zero quantities) so the *rule layer* can emit precise bilingual
errors instead of raw pydantic exceptions. Intake paths (M3) must map VAT columns
explicitly and fail per-row when they can't.

### D-018 · Declared values are cross-checked, never coerced
`declared_net_amount` / `declared_vat_amount` per line and the three
`declared_total_*` header fields hold customer-supplied numbers (e.g. CSV columns).
Rules compare them with computed values and report mismatches with both numbers;
the XML always uses computed values, and generation is refused while any rule
fails — nothing is silently "fixed".

### D-019 · Arithmetic & rounding policy (v1)
ROUND_HALF_UP to 2 decimals (fils); line net rounded once at line level
(`round2(qty*price − discount)`); VAT computed **per category** from the category
taxable sum (EN 16931 convention), not by summing per-line VAT — the
`valid_rounding_edge` golden fixture locks the case where the two differ.
SPEC-CHECK markers sit on both assumptions.

### D-020 · v1 scope restrictions: AED only, type code 380 only
Non-AED currencies and non-380 type codes are *validation errors* (bilingual),
not silent acceptance. Foreign currency needs TaxCurrencyCode + exchange rates;
credit notes (381) belong to the Phase-2 corrections workflow.

### D-021 · Unit-price precision preserved; sub-fils discounts rejected
Caught in golden-file review: the 2-decimal formatter was rounding a 0.105 unit
price to 0.10 — silent data change. Unit prices now keep full precision in
`cbc:PriceAmount` (EN 16931 allows it for unit prices only). Discounts are
monetary amounts that must fit the 2-decimal XML, so >2-decimal discounts are
rejected via `invoice.line.discount_invalid` instead of being rounded.

### D-022 · Golden files are the engine's contract
15 fixtures (6 valid incl. rounding edge case + 9 error classes) under
`backend/tests/golden/`; exact XML bytes and exact bilingual error lists are
committed. `scripts/regen_golden.py` regenerates outputs after intentional engine
changes — diffs must be reviewed line-by-line and justified by a spec reference.

### D-023 · Spec version label
Internal label `pint-ae-1.0` (engine class `PintAeV1Engine`, default in settings).
Each generated XML carries its spec version (`GeneratedXml.spec_version`); M4
transmissions will persist it per send. Registry proves a v2 can be added without
touching v1 (tested).

### SPEC-CHECK register (M2) — to verify against the official MoF spec
1. `CustomizationID` = `urn:peppol:pint:billing-1@ae-1`, `ProfileID` =
   `urn:peppol:bis:billing` (serializer.py).
2. Rounding mode ROUND_HALF_UP to fils (calc.py).
3. Per-category VAT computation à la EN 16931 (calc.py).
4. UAE standard rate fixed at 5%; category set S/Z/E/AE — more categories (e.g.
   'O' out of scope) may be required (calc.py, canonical.py).
5. Buyer TRN mandatory = B2B "standard invoice" assumption (rules.py).
6. Peppol participant scheme ID for UAE (EndpointID schemeID, e.g. "0235") —
   confirm with ASP (canonical.py, serializer.py).
7. Bilingual content: Arabic party name as second `cac:PartyName`, Arabic line
   description as `cbc:Description` (serializer.py).
8. Percent formatting short form ("5" not "5.00") (serializer.py).
9. Unit-price extra precision carried over from EN 16931 (serializer.py).
10. Official spec version identifier ↔ internal `pint-ae-1.0` label (config.py,
    v1/__init__.py).
