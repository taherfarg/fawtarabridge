export interface ErrorDetail {
  code: string;
  field?: string | null;
  message_en: string;
  message_ar: string;
  suggestion_en?: string | null;
  suggestion_ar?: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  phone_verified: boolean;
}

export interface TenantOut {
  id: string;
  legal_name_ar: string;
  legal_name_en: string;
  trn: string;
  license_no?: string | null;
  emirate?: string | null;
  address?: string | null;
  revenue_band: "gte_50m" | "lt_50m" | "unknown";
  status: string;
  asp_participant_id?: string | null;
  asp_onboarding_status: string;
}

export type InvoiceStatus =
  | "DRAFT"
  | "VALIDATED"
  | "QUEUED"
  | "SENT"
  | "ACCEPTED"
  | "REJECTED"
  | "ERROR";

export interface InvoiceOut {
  id: string;
  invoice_number: string;
  status: InvoiceStatus;
  issue_date: string;
  buyer_name: string;
  buyer_trn?: string | null;
  total_including_vat: string;
  duplicate_warning: boolean;
  spec_version?: string | null;
  buyer_contact_id?: string | null;
}

export interface InvoiceLine {
  line_id?: string | null;
  description: string;
  description_ar?: string | null;
  quantity: string;
  unit_code?: string;
  unit_price: string;
  discount_amount?: string;
  vat_category: "S" | "Z" | "E" | "AE" | "O";
  vat_rate: string;
  exemption_reason?: string | null;
}

export interface CanonicalParty {
  name: string;
  name_ar?: string | null;
  trn?: string | null;
  peppol_id?: string | null;
  address: { street?: string | null; city?: string | null; emirate?: string | null; country_code: string };
}

export interface CanonicalInvoice {
  invoice_number: string;
  issue_date: string;
  due_date?: string | null;
  note?: string | null;
  currency: string;
  supplier: CanonicalParty;
  buyer: CanonicalParty;
  lines: InvoiceLine[];
}

export interface TransmissionOut {
  id: string;
  status: string;
  attempt_count: number;
  asp_message_id?: string | null;
  rejection?: ErrorDetail | null;
  last_error?: string | null;
  created_at: string;
}

export interface InvoiceDetailOut extends InvoiceOut {
  canonical: CanonicalInvoice;
  errors: ErrorDetail[];
  warnings: ErrorDetail[];
  latest_transmission?: TransmissionOut | null;
}

export interface InvoiceCreateOut {
  invoice: InvoiceOut;
  errors: ErrorDetail[];
  warnings: ErrorDetail[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContactOut {
  id: string;
  name_en: string;
  name_ar?: string | null;
  trn?: string | null;
  email?: string | null;
  phone?: string | null;
  city?: string | null;
  emirate?: string | null;
  country_code: string;
  default_vat_category?: string | null;
}

export interface AuditEventOut {
  id: string;
  action: string;
  actor_type: string;
  before?: Record<string, unknown> | null;
  after?: Record<string, unknown> | null;
  created_at: string;
}

export interface ComplianceSummary {
  period: string;
  total_invoices: number;
  counts: Record<InvoiceStatus, number>;
  accepted_total_aed: string;
  unsent_past_due: number;
  penalty_risk_aed: number;
  penalty_cap_aed: number;
  currency: string;
}

export interface MemberOut {
  user: UserOut;
  role: "owner" | "accountant" | "staff" | "readonly";
}

export interface ImportInvoiceReport {
  invoice_number: string;
  rows: number[];
  valid: boolean;
  errors: ErrorDetail[];
  warnings: ErrorDetail[];
  invoice_id?: string | null;
}

export interface ImportReport {
  summary: { rows: number; invoices: number; valid: number; invalid: number; created: number };
  file_errors: ErrorDetail[];
  row_issues: { row: number; errors: ErrorDetail[] }[];
  invoices: ImportInvoiceReport[];
  saved_template_id?: string | null;
}

export interface MappingTemplateOut {
  id: string;
  name: string;
  mapping: ImportMapping;
}

export interface ImportMapping {
  columns: Record<string, string | null>;
  vat_value_map: Record<string, string>;
  date_format: string;
}

export interface ValidationReport {
  status: InvoiceStatus;
  spec_version?: string | null;
  errors: ErrorDetail[];
  warnings: ErrorDetail[];
}
