# Product Requirements Document (PRD)
## "FawtaraBridge" — UAE E-Invoicing Compliance SaaS for SMEs
**Version:** 1.0 | **Date:** June 2026 | **Owner:** Taher Farg Ibrahim | **Status:** Draft for build

---

## 1. Executive Summary

FawtaraBridge is a B2B SaaS that makes UAE SMEs compliant with the mandatory national Electronic Invoicing System (EIS). It ingests invoices in whatever form an SME can produce (Excel, PDF, photo, manual entry), converts them to valid PINT-AE XML, transmits them through a partnered FTA-accredited Accredited Service Provider (ASP) over the Peppol 5-corner network, and gives owners a bilingual (Arabic-first) dashboard with WhatsApp alerts for rejections and deadlines.

**Why now:** Pilot phase began July 2026; large businesses (AED 50M+ revenue) are mandated from January 2027; SMEs (~94% of the UAE's 1.4M registered businesses) follow July 2027. Penalties: AED 5,000/month for non-implementation; AED 100 per non-transmitted invoice. PDF/Excel/email invoices will no longer be compliant.

**What we are NOT:** We are not an ASP (accreditation requires Peppol certification + 2 years operating history). We are the integration and usability layer on top of an ASP.

---

## 2. Goals & Success Metrics

### Business goals (12 months post-launch)
| Metric | Target |
|---|---|
| Paying customers | 100 |
| MRR | AED 25,000+ |
| Channel partners (accounting firms) | 5+ active |
| Logo churn | < 2%/month |
| Invoice transmission success rate | > 99% accepted by ASP on first or second attempt |

### Product goals
- An SME owner with zero technical skill can go from signup → first compliant invoice transmitted in **under 30 minutes**.
- OCR/LLM extraction achieves ≥ 95% field-level accuracy on printed invoices; 100% of low-confidence fields routed to human review (never auto-submit uncertain data).
- All invoice data stored in-country (UAE data residency) and retained ≥ 5 years per regulation.

---

## 3. Users & Personas

### P1 — SME Owner ("Abu Khalid")
Trading company / contractor / clinic / workshop, 1–50 staff, 50–500 invoices/month. Invoices from Excel or Word. Arabic-first, runs his business on WhatsApp. Motivated by fear of fines, not love of software. Needs: simplicity, Arabic UI, proof of compliance.

### P2 — Accountant / Tax Consultant ("Sara")
Manages 20–100 SME clients. Needs a multi-client console, bulk onboarding, client compliance status at a glance, white-label option, and a referral commission. She is the primary **sales channel**, not just a user.

### P3 — SME Staff / Bookkeeper
Day-to-day invoice entry/upload. Needs fast bulk upload, clear error messages in plain language, and an audit trail so blame is never ambiguous.

### P4 — Internal Admin (us)
Tenant management, ASP credential management, extraction-review queue monitoring, usage/billing oversight, spec-version management.

---

## 4. Scope

### 4.1 MVP (Phase 1 — weeks 1–8)
1. Multi-tenant auth & company onboarding (TRN, entity details, Peppol participant registration via ASP)
2. Invoice intake: CSV/Excel upload with column-mapping wizard; manual entry form; single-invoice quick form
3. PINT-AE XML generation engine + full schema/business-rule validation with human-readable bilingual errors
4. Integration with ONE pre-approved ASP (target: Flick Network or ClearTax/Defmacro) — send, receive status callbacks, receive inbound invoices
5. Compliance dashboard: invoice statuses (draft / validated / sent / accepted / rejected), monthly summary, penalty-risk indicator
6. WhatsApp + email alerts: rejections, action required, deadline reminders
7. 5-year immutable archive with search & export (XML + human-readable PDF rendering)
8. Billing: subscription tiers via Stripe (card) — Starter / Growth / Accountant

### 4.2 Phase 2 (months 3–6)
9. OCR + LLM extraction pipeline for PDF/photo invoices with confidence scoring and human-review screen
10. Accountant multi-client console + white-label theming + commission tracking
11. Inbound invoice management (receive supplier e-invoices, approve, archive)
12. Credit notes & corrections workflow
13. Tally / QuickBooks / Zoho Books import connectors (file-based first, API later)

### 4.3 Phase 3 (months 6–12)
14. Corporate Tax assistant module (CT computation from invoice ledger, Small Business Relief eligibility check, EmaraTax-prep outputs)
15. Second ASP integration (redundancy + pricing leverage) behind the existing adapter interface
16. VAT return preparation summary
17. Public API + webhooks for partners
18. Mobile-responsive PWA polish (no native app)

### 4.4 Explicitly out of scope
Full accounting/ERP, payroll/WPS, KSA ZATCA (future expansion only), native mobile apps, becoming an ASP, payments processing between businesses.

---

## 5. Functional Requirements

### FR-1 Onboarding & Tenant Setup
- FR-1.1 Email + password and Google sign-in; mandatory phone (WhatsApp) verification via OTP.
- FR-1.2 Company profile: legal name (AR/EN), TRN (15-digit validation), license number, emirate, address, revenue band (drives deadline messaging).
- FR-1.3 Trigger Peppol participant onboarding with partnered ASP via API; surface ASP onboarding status in UI.
- FR-1.4 Roles: Owner, Accountant, Staff, Read-only. Accountant role can be linked across multiple tenants.
- FR-1.5 Guided setup checklist with progress bar; bilingual; completable in < 30 min.

### FR-2 Invoice Intake
- FR-2.1 Excel/CSV bulk upload: column-mapping wizard with saved mapping templates per tenant; preview + per-row validation before commit.
- FR-2.2 Manual invoice form with line items, VAT rate per line (5%, 0%, exempt, reverse charge), discounts, buyer TRN lookup from saved contacts.
- FR-2.3 Buyer/customer address book with TRN validation and Peppol ID resolution (via ASP directory lookup where available).
- FR-2.4 (Phase 2) PDF/image upload → OCR → LLM field extraction → confidence-scored result. Fields below threshold (default 0.90) flagged for human review. NEVER transmit an invoice containing an unreviewed low-confidence field.
- FR-2.5 Duplicate detection: warn on same buyer + amount + date ± configurable window.

### FR-3 PINT-AE Engine (core IP)
- FR-3.1 Internal canonical invoice model (Pydantic) — single source of truth; all intake paths normalize into it.
- FR-3.2 Serializer: canonical model → PINT-AE-compliant UBL XML per the current Ministry of Finance specification.
- FR-3.3 Validation: XSD schema validation + Schematron/business rules (TRN formats, VAT arithmetic, mandatory fields, rounding rules, currency rules).
- FR-3.4 Error mapping table: every validation code → plain-language Arabic + English message + suggested fix.
- FR-3.5 Spec versioning: engine supports multiple spec versions concurrently; version pinned per transmission; hot-swappable on MoF updates.
- FR-3.6 Golden-file test suite built from official MoF/Peppol sample documents; CI gate — no deploy if any golden test fails.

### FR-4 ASP Transmission Layer
- FR-4.1 Abstract `ASPAdapter` interface: `register_participant()`, `send_invoice()`, `get_status()`, `receive_inbound()`, `lookup_participant()`. ASP #1 is the first implementation; design for N.
- FR-4.2 Async queue (Celery/Redis): retries with exponential backoff; idempotency keys per invoice; dead-letter queue with admin alerting.
- FR-4.3 Status lifecycle: DRAFT → VALIDATED → QUEUED → SENT → ACCEPTED / REJECTED / ERROR, with full timestamped audit trail per transition (who/what/when).
- FR-4.4 Rejection handling: parse ASP/FTA rejection reasons → bilingual explanation → one-click "fix & resend" flow.
- FR-4.5 Inbound invoices from suppliers stored, rendered human-readably, and surfaced in dashboard (Phase 2 approval flow).

### FR-5 Dashboard & Reporting
- FR-5.1 Home: compliance health score, invoices this month by status, pending actions, days-to-deadline banner based on revenue band.
- FR-5.2 Invoice list: filter by status/date/buyer/amount; bulk actions; XML + PDF download per invoice.
- FR-5.3 Monthly compliance report (PDF, bilingual) — designed to be forwarded to the owner's accountant.
- FR-5.4 Penalty-risk indicator: estimated exposure if currently non-compliant invoices remain unsent (AED 100/invoice logic, capped per regulation).

### FR-6 Notifications
- FR-6.1 WhatsApp Business API: rejection alerts, action-required, weekly digest, regulatory deadline reminders. Template messages pre-approved in AR + EN.
- FR-6.2 Email fallback for all WhatsApp notifications.
- FR-6.3 Per-user notification preferences; Owner cannot disable rejection alerts (compliance-critical).

### FR-7 Archive & Audit
- FR-7.1 Immutable storage of transmitted XML + rendered PDF + ASP acknowledgement for ≥ 5 years (write-once object storage, UAE region).
- FR-7.2 Full-text and structured search across archive.
- FR-7.3 One-click full export (ZIP of XMLs + index CSV) for FTA audit requests.
- FR-7.4 Append-only audit log of every user and system action on every invoice.

### FR-8 Billing & Plans
- FR-8.1 Plans: Starter AED 149/mo (≤100 invoices), Growth AED 349/mo (≤500, OCR, multi-user), Accountant AED 999/mo (≤20 client companies, white-label). 14-day free trial, no card required.
- FR-8.2 Usage metering per tenant per month; soft-warning at 80%, hard prompt to upgrade at 100% (never block a compliance-critical transmission mid-month — bill overage at AED 1/invoice instead).
- FR-8.3 Stripe subscriptions; invoices for our own service must themselves be e-invoicing compliant (dogfooding).

### FR-9 Admin Console (internal)
- FR-9.1 Tenant overview, impersonation with audit logging, plan overrides.
- FR-9.2 Extraction review queue metrics; spec-version management; ASP health monitoring; DLQ inspection/replay.

---

## 6. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Data residency | All invoice data, archives, and backups in UAE region (AWS me-central-1 or Azure UAE North). No cross-border persistence. |
| Security | Encryption at rest (AES-256) and in transit (TLS 1.2+); secrets in a vault; per-tenant row-level isolation (tenant_id enforced at ORM + DB policy level); OWASP ASVS L2 target. |
| Auth | Bcrypt/Argon2 passwords, optional TOTP 2FA, session revocation, rate limiting on auth endpoints. |
| Availability | 99.5% target for MVP; transmission queue must survive app restarts (durable broker). |
| Performance | Dashboard < 2s p95; bulk upload of 1,000 rows processed < 5 min; single invoice validate < 2s. |
| Localization | Full RTL Arabic + English; Arabic is the default; all validation errors, emails, WhatsApp templates bilingual. Hijri date display optional, Gregorian canonical. |
| Compliance | 5-year retention; append-only audit logs; PINT-AE spec-version traceability per invoice. |
| Privacy | UAE PDPL alignment: data processing register, DPA template for accountant partners, deletion policy (post-retention). |
| Observability | Structured logging, Sentry error tracking, uptime monitoring, per-ASP success-rate dashboards. |
| Backups | Daily encrypted snapshots, 30-day point-in-time recovery, restore drill quarterly. |

---

## 7. System Architecture

```
[React SPA (AR-first RTL)]
        │ HTTPS/JSON
[FastAPI Gateway] ── [Auth/JWT] ── [PostgreSQL (multi-tenant, RLS)]
        │                               │
        ├── [Intake Service] ── (Excel parser / manual / OCR+LLM pipeline*)
        ├── [PINT-AE Engine] ── (canonical model → XML → XSD+Schematron)
        ├── [ASP Adapter Layer] ── Celery/Redis queue ──► [ASP API (Peppol 5-corner)] ──► FTA
        ├── [Notification Service] ──► WhatsApp Business API / SMTP
        └── [Archive Service] ──► UAE-region object storage (WORM/immutable)
* OCR: Azure Document Intelligence (UAE) or self-hosted Tesseract + OpenCV preprocessing;
  LLM structuring via API with confidence scoring; human-review UI for low-confidence fields.
```

**Key design decisions**
1. **Canonical invoice model first.** Every intake path converges to one Pydantic model; the XML engine consumes only that. Keeps the core testable and spec changes localized.
2. **ASP behind an adapter.** Switching/adding ASPs is a plugin, not a rewrite.
3. **Queue everything outbound.** Transmission is async, idempotent, retried; the UI never blocks on the ASP.
4. **Human-in-the-loop on extraction.** Confidence thresholds + review queue. Compliance product = correctness over convenience.
5. **Spec versioning as a feature.** Regulations will change; version pinning + golden tests turn churn into a selling point.

---

## 8. Data Model (core entities)

- **Tenant** (company): id, legal_name_ar/en, trn, license_no, emirate, revenue_band, asp_participant_id, plan, status
- **User**: id, email, phone_whatsapp, role, tenant links (M:N for accountants)
- **Contact** (buyer/supplier): trn, names, address, peppol_id, default VAT treatment
- **Invoice**: id, tenant_id, direction (out/in), canonical JSON, status, spec_version, totals, currency, issue_date, idempotency_key
- **InvoiceLine**: description_ar/en, qty, unit_price, vat_rate, vat_amount, discounts
- **Transmission**: invoice_id, asp, request/response payload refs, attempt_no, result_code, timestamps
- **ArchiveObject**: invoice_id, xml_uri, pdf_uri, ack_uri, hash, retention_until
- **AuditEvent**: actor, action, entity, before/after hash, timestamp (append-only)
- **ExtractionJob** (Phase 2): file_uri, ocr_output, llm_output, field confidences, review_status, reviewer_id
- **Subscription/UsageRecord**: plan, period, invoice_count, overage

---

## 9. Key API Surface (internal, v1)

```
POST /auth/signup | /auth/login | /auth/otp
POST /tenants/{id}/onboard-asp
POST /invoices              (create from canonical/manual)
POST /invoices/import       (Excel/CSV with mapping_id)
POST /invoices/extract      (file upload → ExtractionJob)   [Phase 2]
POST /invoices/{id}/validate
POST /invoices/{id}/send
GET  /invoices?status=&from=&to=&buyer=
GET  /invoices/{id}/xml | /pdf | /audit
POST /webhooks/asp/{provider}   (status callbacks, signed)
GET  /reports/monthly?period=
GET  /compliance/summary
```

---

## 10. Milestones & Timeline

| Week | Deliverable |
|---|---|
| 0 | ASP partnership emails sent (Flick, ClearTax, +1); sandbox access requested; free-zone license application started |
| 1–2 | Repo, CI, multi-tenant auth, tenant onboarding, DB schema |
| 2–4 | PINT-AE engine + golden-file test suite (CORE — do this before UI polish) |
| 3–5 | Excel import wizard + manual entry + contacts |
| 4–6 | ASP adapter + queue + status lifecycle against sandbox |
| 5–7 | Dashboard, archive, WhatsApp/email alerts |
| 7–8 | Billing, trial flow, bilingual polish, security pass, pilot onboarding docs |
| 8 | **MVP live — pilot with 5–10 friendly businesses (free)** |
| 9–16 | Pilot hardening; OCR/LLM extraction; accountant console v1; convert pilots to paid |
| 16–28 | Channel partner program (5 firms); inbound invoices; credit notes; 50 customers |
| 28–52 | CT assistant module; 2nd ASP; public API; 100 customers / AED 25k MRR |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| ASP partnership delayed / unfavorable terms | Med | Approach 3 ASPs in parallel; adapter layer keeps switching cheap |
| MoF spec changes mid-build | High | Spec-version engine + golden tests; subscribe to MoF/FTA bulletins; budget 15% ongoing eng time |
| Big vendors launch cheap SME tier | Med | Win on Arabic-first UX, WhatsApp workflow, OCR intake, accountant channel |
| SMEs procrastinate until 2027 | High | Accountant channel converts in batches; pricing anchored to AED 5,000/mo penalty; content engine builds brand early |
| Extraction errors → wrong data to FTA | Low if controlled | Confidence thresholds, mandatory human review, never auto-submit uncertain fields, full audit trail |
| Solo-founder bandwidth | High | Ruthless MVP scope; no native apps; buy (Stripe, WhatsApp BSP, managed DB) over build |
| Non-compete / employment conflict | Med | Review Pollux contract before public launch; free-zone license; legal consult AED ~1–2k |

---

## 12. Open Questions
1. Which ASP offers the best per-invoice pricing + sandbox quality? (Decision gate: end of week 2)
2. WhatsApp BSP choice (360dialog vs Twilio vs Meta direct) — cost & template approval speed in UAE.
3. OCR: Azure Document Intelligence UAE region availability/pricing vs self-hosted pipeline.
4. Exact penalty cap mechanics for the risk indicator — confirm against Cabinet Resolution 106 of 2025 text.
5. Brand name & domain (working title "FawtaraBridge" — validate trademark availability in UAE).

---

## 13. Definition of Done (MVP)
- A pilot business uploads an Excel of 50 real invoices, fixes flagged errors via bilingual messages, transmits all 50 through the ASP sandbox→production, sees ACCEPTED statuses, receives a WhatsApp confirmation, and downloads a monthly compliance PDF — with zero developer intervention.
