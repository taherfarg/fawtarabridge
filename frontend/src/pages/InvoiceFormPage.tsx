import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type {
  ContactOut,
  ErrorDetail,
  InvoiceCreateOut,
  InvoiceDetailOut,
  InvoiceLine,
  Paged,
} from "../api/types";
import { ErrorList, errorsOf, money } from "../components/ui";

const VAT_RATES: Record<string, string> = { S: "5", Z: "0", E: "0", AE: "0" };

function emptyLine(): InvoiceLine {
  return { description: "", quantity: "1", unit_price: "0", discount_amount: "0", vat_category: "S", vat_rate: "5" };
}

export default function InvoiceFormPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(id);

  const [number, setNumber] = useState("");
  const [issueDate, setIssueDate] = useState(new Date().toISOString().slice(0, 10));
  const [dueDate, setDueDate] = useState("");
  const [note, setNote] = useState("");
  const [buyerMode, setBuyerMode] = useState<"contact" | "manual">("contact");
  const [contactId, setContactId] = useState("");
  const [buyerName, setBuyerName] = useState("");
  const [buyerNameAr, setBuyerNameAr] = useState("");
  const [buyerTrn, setBuyerTrn] = useState("");
  const [lines, setLines] = useState<InvoiceLine[]>([emptyLine()]);
  const [errors, setErrors] = useState<ErrorDetail[]>([]);
  const [warnings, setWarnings] = useState<ErrorDetail[]>([]);
  const [busy, setBusy] = useState(false);

  const contacts = useQuery({
    queryKey: ["contacts", "all"],
    queryFn: () => api.get<Paged<ContactOut>>("/contacts?limit=200"),
  });
  const existing = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => api.get<InvoiceDetailOut>(`/invoices/${id}`),
    enabled: editing,
  });

  useEffect(() => {
    const data = existing.data;
    if (!data) return;
    setNumber(data.canonical.invoice_number);
    setIssueDate(data.canonical.issue_date);
    setDueDate(data.canonical.due_date ?? "");
    setNote(data.canonical.note ?? "");
    setLines(data.canonical.lines.map((line) => ({ ...line, discount_amount: line.discount_amount ?? "0" })));
    if (data.buyer_contact_id) {
      setBuyerMode("contact");
      setContactId(data.buyer_contact_id);
    } else {
      setBuyerMode("manual");
      setBuyerName(data.canonical.buyer.name);
      setBuyerNameAr(data.canonical.buyer.name_ar ?? "");
      setBuyerTrn(data.canonical.buyer.trn ?? "");
    }
  }, [existing.data]);

  function setLine(index: number, patch: Partial<InvoiceLine>) {
    setLines((current) =>
      current.map((line, i) => {
        if (i !== index) return line;
        const next = { ...line, ...patch };
        if (patch.vat_category) next.vat_rate = VAT_RATES[patch.vat_category];
        return next;
      }),
    );
  }

  const estimated = lines.reduce((sum, line) => {
    const net = Number(line.quantity) * Number(line.unit_price) - Number(line.discount_amount ?? 0);
    const vat = line.vat_category === "S" ? net * 0.05 : 0;
    return sum + (Number.isFinite(net) ? net + vat : 0);
  }, 0);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setWarnings([]);
    const payload = {
      invoice_number: number,
      issue_date: issueDate,
      due_date: dueDate || null,
      note: note || null,
      buyer_contact_id: buyerMode === "contact" ? contactId || null : null,
      buyer:
        buyerMode === "manual"
          ? { name: buyerName, name_ar: buyerNameAr || null, trn: buyerTrn || null }
          : null,
      lines,
    };
    try {
      const result = editing
        ? await api.put<InvoiceCreateOut>(`/invoices/${id}`, payload)
        : await api.post<InvoiceCreateOut>("/invoices", payload);
      if (result.errors.length > 0 || result.warnings.length > 0) {
        setErrors(result.errors);
        setWarnings(result.warnings);
        if (result.errors.length > 0) {
          setBusy(false);
          if (!editing) navigate(`/invoices/${result.invoice.id}/edit`, { replace: true });
          return;
        }
      }
      navigate(`/invoices/${result.invoice.id}`);
    } catch (err) {
      setErrors(errorsOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5 max-w-4xl">
      <h1 className="text-2xl font-bold">
        {editing ? t("form.editTitle", { number }) : t("form.title")}
      </h1>

      <div className="card grid md:grid-cols-3 gap-4">
        <div>
          <label className="label">{t("invoices.number")}</label>
          <input className="input" dir="ltr" required value={number} onChange={(e) => setNumber(e.target.value)} />
        </div>
        <div>
          <label className="label">{t("invoices.issueDate")}</label>
          <input className="input" type="date" required value={issueDate} onChange={(e) => setIssueDate(e.target.value)} />
        </div>
        <div>
          <label className="label">
            {t("invoices.dueDate")} <span className="text-slate-400">({t("common.optional")})</span>
          </label>
          <input className="input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </div>
        <div className="md:col-span-3">
          <label className="label">
            {t("invoices.noteLabel")} <span className="text-slate-400">({t("common.optional")})</span>
          </label>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>

      <div className="card space-y-4">
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input type="radio" checked={buyerMode === "contact"} onChange={() => setBuyerMode("contact")} />
            {t("form.buyerFromContacts")}
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" checked={buyerMode === "manual"} onChange={() => setBuyerMode("manual")} />
            {t("form.buyerManual")}
          </label>
        </div>
        {buyerMode === "contact" ? (
          <select className="input" required value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">{t("form.selectContact")}</option>
            {contacts.data?.items.map((contact) => (
              <option key={contact.id} value={contact.id}>
                {contact.name_en} {contact.trn ? `(${contact.trn})` : ""}
              </option>
            ))}
          </select>
        ) : (
          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <label className="label">{t("form.buyerName")}</label>
              <input className="input" required value={buyerName} onChange={(e) => setBuyerName(e.target.value)} />
            </div>
            <div>
              <label className="label">{t("contacts.nameAr")}</label>
              <input className="input" dir="rtl" value={buyerNameAr} onChange={(e) => setBuyerNameAr(e.target.value)} />
            </div>
            <div>
              <label className="label">{t("form.buyerTrn")}</label>
              <input className="input" dir="ltr" maxLength={15} value={buyerTrn} onChange={(e) => setBuyerTrn(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold">{t("invoices.lines")}</h2>
        {lines.map((line, index) => (
          <div key={index} className="grid md:grid-cols-12 gap-2 items-end border-b border-slate-100 pb-3">
            <div className="md:col-span-3">
              <label className="label">{t("form.description")}</label>
              <input className="input" required value={line.description} onChange={(e) => setLine(index, { description: e.target.value })} />
            </div>
            <div className="md:col-span-2">
              <label className="label">{t("form.descriptionAr")}</label>
              <input className="input" dir="rtl" value={line.description_ar ?? ""} onChange={(e) => setLine(index, { description_ar: e.target.value || null })} />
            </div>
            <div>
              <label className="label">{t("form.qty")}</label>
              <input className="input" dir="ltr" value={line.quantity} onChange={(e) => setLine(index, { quantity: e.target.value })} />
            </div>
            <div className="md:col-span-2">
              <label className="label">{t("form.unitPrice")}</label>
              <input className="input" dir="ltr" value={line.unit_price} onChange={(e) => setLine(index, { unit_price: e.target.value })} />
            </div>
            <div>
              <label className="label">{t("form.discount")}</label>
              <input className="input" dir="ltr" value={line.discount_amount} onChange={(e) => setLine(index, { discount_amount: e.target.value })} />
            </div>
            <div className="md:col-span-2">
              <label className="label">{t("form.vat")}</label>
              <select
                className="input"
                value={line.vat_category}
                onChange={(e) => setLine(index, { vat_category: e.target.value as InvoiceLine["vat_category"] })}
              >
                <option value="S">{t("form.vatS")}</option>
                <option value="Z">{t("form.vatZ")}</option>
                <option value="E">{t("form.vatE")}</option>
                <option value="AE">{t("form.vatAE")}</option>
              </select>
            </div>
            <div>
              <button
                type="button"
                className="btn-secondary w-full"
                disabled={lines.length === 1}
                onClick={() => setLines((current) => current.filter((_, i) => i !== index))}
              >
                ✕
              </button>
            </div>
            {(line.vat_category === "E" || line.vat_category === "AE") && (
              <div className="md:col-span-12">
                <label className="label">{t("form.exemptionReason")}</label>
                <input
                  className="input"
                  required
                  value={line.exemption_reason ?? ""}
                  onChange={(e) => setLine(index, { exemption_reason: e.target.value })}
                />
              </div>
            )}
          </div>
        ))}
        <div className="flex items-center justify-between">
          <button type="button" className="btn-secondary" onClick={() => setLines((c) => [...c, emptyLine()])}>
            + {t("form.addLine")}
          </button>
          <div className="text-sm text-slate-500">
            {t("form.totalsPreview")}: <span className="font-semibold" dir="ltr">AED {money(estimated)}</span>
          </div>
        </div>
      </div>

      {errors.length > 0 && <p className="text-sm text-amber-700">{t("form.fixIssues")}</p>}
      <ErrorList errors={errors} />
      <ErrorList errors={warnings} tone="warning" />

      <button className="btn-primary" disabled={busy}>
        {busy ? t("auth.working") : t("form.save")}
      </button>
    </form>
  );
}
