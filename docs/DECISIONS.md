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

---

## M3 — Intake (2026-06-11)

### D-024 · Supplier identity always derives from the tenant profile
Neither the manual API nor the importer accepts supplier data: the supplier
`Party` is built from the Tenant row (legal names, TRN, address). A client can
never issue an invoice under a different supplier identity than their company
profile. TRN corrections go through the admin flow (D-013).

### D-025 · Drafts persist even when invalid; validation pins the spec version
`POST /invoices` always saves a DRAFT and returns the bilingual error/warning
lists alongside (incomplete drafts are a legitimate workflow state).
`POST /invoices/{id}/validate` flips DRAFT→VALIDATED only when the engine is
clean and pins `spec_version`; any `PUT` re-opens the DRAFT and clears it.
Statuses stay limited to DRAFT/VALIDATED until the M4 state machine. There is no
invoice DELETE endpoint (compliance product; PRD defines none).

### D-026 · Import never guesses: fully explicit mapping
The mapping payload carries the column names, an explicit `vat_value_map`
("5%"→S, "exempt"→E, …) and an explicit `date_format` (default ISO). Unknown VAT
values / unparseable dates / bad numbers are per-row bilingual errors — nothing
is auto-detected or defaulted. Only mechanical normalization is applied:
trimming, thousands separators in numbers, case-insensitive VAT-map keys. The
VAT *rate* is derived from the category via the v1 rate table (deterministic,
not a guess).

### D-027 · Import is a stateless preview/commit pair with partial commit
Both endpoints take file + mapping (or `template_id`); preview persists nothing.
Commit creates every valid invoice as DRAFT and reports the rest — one broken row
never blocks the batch. Each creation runs inside a SAVEPOINT so a constraint
violation (duplicate number) cannot abort the surrounding transaction (found by
test: Postgres poisons the transaction after any failed statement).
`save_template_name` upserts the tenant's mapping template (wizard "save" UX).

### D-028 · Row grouping & line numbering
Rows sharing an invoice-number cell become one invoice's lines, in file order,
auto-numbered "1"…"n". Header cells (date, buyer, declared totals…) must agree
across the group — mismatch flags `import.inconsistent_invoice` for that invoice.
Customer-facing row numbers are 1-based over data rows (header excluded).

### D-029 · No silent contact enrichment in import
The importer builds the buyer purely from file columns; it neither looks up nor
creates contacts (deterministic, no surprise writes). The manual API links
contacts explicitly via `buyer_contact_id`. A "link to contacts" assist can land
in the M6 wizard UI.

### D-030 · Contact model
TRN optional at contact level (invoice-level rules enforce presence for B2B),
unique per tenant when present (partial index → bilingual 409). Hard DELETE is
allowed: invoices keep the full buyer snapshot inside their canonical JSON and
`buyer_contact_id` is `ON DELETE SET NULL`.

### D-031 · Duplicate detection (FR-2.5)
Key = buyer TRN (fallback: exact buyer name) + identical gross total + issue date
within ±3 days, computed against the engine's totals. Result is a warning
(`invoice.possible_duplicate` naming the matched numbers, max 5) and a persisted
`duplicate_warning` flag — creation is never blocked. Window is the fixed 3 days
from the build instructions; per-tenant configurability (PRD "configurable
window") is deferred to settings (M6/M7).

### D-007 · Closed
The promised invoice-level RLS test now exists:
`test_tenant_a_can_never_read_tenant_b_invoices` (SQL-level) plus API-level
isolation tests for contacts and invoices.

No new SPEC-CHECK items in M3 (intake is not spec-bound; the M2 register stands).

---

## M4 — Transmission & lifecycle (2026-06-11)

### D-033 · State machine extensions beyond the spec'd happy path
The instructed lifecycle (DRAFT→VALIDATED→QUEUED→SENT→ACCEPTED|REJECTED|ERROR)
is extended with recovery edges: VALIDATED→DRAFT (edit/re-validation failure),
REJECTED→DRAFT|QUEUED and ERROR→DRAFT|QUEUED (fix-and-resend / direct resend /
dead-letter replay). ACCEPTED is terminal. The transition table is asserted
exhaustively for all 49 (from,to) pairs, and `transition_invoice` is the only
legal way to change a status — it writes the audit event atomically.

### D-034 · Audit immutability enforced by PostgreSQL privileges
`audit_events` has SELECT+INSERT grants only for the app role — UPDATE/DELETE
are *impossible* even for buggy or compromised app code, not merely "not
implemented". Tested (`permission denied`). Events carry actor_id, actor_type
(user/system/asp_webhook), before/after JSON and a server timestamp.

### D-035 · Idempotency model
The API refuses double-queueing via the state machine (only VALIDATED can be
sent). Each transmission carries `idempotency_key =
"<tenant>:<invoice>:<xml-hash16>:<ordinal>"` to the ASP, so broker re-deliveries
and network retries can never double-deliver (mock dedupes on it; real ASPs
support the same). Re-executing a finalized transmission is a no-op
(`task_acks_late` + at-least-once semantics). The tenant prefix doubles as the
webhook's RLS context — no bypass role exists for callbacks either.

### D-036 · Retry/backoff/dead-letter mechanics
`execute_transmission` is a plain function (unit-testable without a broker); the
Celery task only schedules retries with exponential backoff (30s·2^n, capped at
30 min). Transient ASP errors retry up to `transmission_max_attempts` (5), then
the transmission dead-letters and the invoice transitions to ERROR. Permanent
errors and engine validation failures fail immediately (no retry). Dead-lettered
and failed transmissions are visible at `GET /transmissions/dead-letter`
(OWNER/ACCOUNTANT); recovery = fix+send or direct resend. The internal admin
console (FR-9) will add the cross-tenant view later.

### D-037 · Worker RLS context
Tasks receive `(transmission_id, tenant_id)` and open `tenant_session(tenant_id)`
— the worker operates under the same RLS policies as the API; there is no
superuser path in the runtime. Tasks are enqueued only after the API commits
(visible row for the worker; in eager test mode the task runs inline).

### D-038 · Mock ASP behavior keyed on receiver TRN suffix
…99 → reject BR-AE-02 · …98 → reject BR-CO-15 · …97 → transient error ·
…96 → permanent error · …94 → stays processing (webhook completes it) · else
accepted. Deterministic, demoable, and exercises every lifecycle path.

### D-039 · Webhook contract (until the real ASP defines one)
HMAC-SHA256 over the raw body in `X-ASP-Signature` (constant-time compare,
shared secret in settings). Payload carries our idempotency_key + status (+
rejection code/reason). Duplicate callbacks are acknowledged as "ignored".
SPEC-CHECK: adapt signing + payload to the contracted ASP's scheme.

### SPEC-CHECK register (M4 additions)
11. Rejection-code list is EN 16931/Peppol BR-*-style placeholder — replace with
    the contracted ASP/FTA code list (asp/rejections.py, asp/mock.py).
12. Peppol participant scheme "0235:<TRN>" placeholder (asp/mock.py).
13. Webhook signing scheme per real ASP (asp/webhook.py).
