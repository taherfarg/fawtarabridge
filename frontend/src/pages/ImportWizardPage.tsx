import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ErrorDetail, ImportReport, MappingTemplateOut } from "../api/types";
import { ErrorList, errorsOf, localizedMessage } from "../components/ui";

const REQUIRED_FIELDS = [
  "invoice_number",
  "issue_date",
  "buyer_name",
  "description",
  "quantity",
  "unit_price",
  "vat_treatment",
] as const;
const OPTIONAL_FIELDS = [
  "buyer_trn",
  "discount_amount",
  "exemption_reason",
  "due_date",
  "note",
  "line_net",
  "line_vat",
  "total_excluding_vat",
  "total_vat",
  "total_including_vat",
] as const;

export default function ImportWizardPage() {
  const { t, i18n } = useTranslation();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [dateFormat, setDateFormat] = useState("%d/%m/%Y");
  const [vatMap, setVatMap] = useState<{ raw: string; category: string }[]>([
    { raw: "5%", category: "S" },
    { raw: "0%", category: "Z" },
  ]);
  const [saveAs, setSaveAs] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [committed, setCommitted] = useState(false);
  const [errors, setErrors] = useState<ErrorDetail[]>([]);
  const [busy, setBusy] = useState(false);

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: () => api.get<MappingTemplateOut[]>("/import/templates"),
  });

  async function onFile(selected: File) {
    setFile(selected);
    setHeaders([]);
    if (selected.name.toLowerCase().endsWith(".csv")) {
      const text = await selected.text();
      const firstLine = text.split(/\r?\n/)[0] ?? "";
      setHeaders(firstLine.split(",").map((h) => h.trim()).filter(Boolean));
    }
  }

  function buildPayload(): string {
    if (templateId) {
      const extra = saveAs ? { save_template_name: saveAs } : {};
      return JSON.stringify({ template_id: templateId, ...extra });
    }
    const mappedColumns: Record<string, string | null> = {};
    for (const field of [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS]) {
      mappedColumns[field] = columns[field] || null;
    }
    const vatValueMap: Record<string, string> = {};
    for (const entry of vatMap) if (entry.raw.trim()) vatValueMap[entry.raw.trim()] = entry.category;
    return JSON.stringify({
      mapping: { columns: mappedColumns, vat_value_map: vatValueMap, date_format: dateFormat },
      ...(saveAs ? { save_template_name: saveAs } : {}),
    });
  }

  async function run(endpoint: "preview" | "commit") {
    if (!file) return;
    setBusy(true);
    setErrors([]);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("payload", buildPayload());
      const result = await api.postForm<ImportReport>(`/invoices/import/${endpoint}`, form);
      setReport(result);
      if (endpoint === "commit") {
        setCommitted(true);
        setStep(4);
      } else {
        setStep(3);
      }
    } catch (err) {
      setErrors(errorsOf(err));
    } finally {
      setBusy(false);
    }
  }

  function columnSelect(field: string, required: boolean) {
    const value = columns[field] ?? "";
    const onChange = (v: string) => setColumns((c) => ({ ...c, [field]: v }));
    return (
      <div key={field}>
        <label className="label">
          {t(`import.fields.${field}`)}
          {!required && <span className="text-slate-400"> ({t("common.optional")})</span>}
        </label>
        {headers.length > 0 ? (
          <select className="input" required={required} value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="">{required ? "—" : t("import.notMapped")}</option>
            {headers.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        ) : (
          <input className="input" dir="ltr" required={required} value={value} onChange={(e) => onChange(e.target.value)} />
        )}
      </div>
    );
  }

  const steps = ["step1", "step2", "step3", "step4"];

  return (
    <div className="space-y-5 max-w-4xl">
      <h1 className="text-2xl font-bold">{t("import.title")}</h1>
      <div className="flex gap-2 text-sm">
        {steps.map((key, index) => (
          <span
            key={key}
            className={`rounded-full px-3 py-1 ${step === index + 1 ? "bg-emerald-700 text-white" : "bg-slate-200 text-slate-600"}`}
          >
            {t(`import.${key}`)}
          </span>
        ))}
      </div>
      <ErrorList errors={errors} />

      {step === 1 && (
        <div className="card space-y-4">
          <div>
            <label className="label">{t("import.chooseFile")}</label>
            <input
              className="input"
              type="file"
              accept=".csv,.xlsx"
              onChange={(e) => e.target.files?.[0] && void onFile(e.target.files[0])}
            />
          </div>
          <div>
            <label className="label">{t("import.template")}</label>
            <select className="input" value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">{t("import.noTemplate")}</option>
              {templates.data?.map((template) => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </select>
          </div>
          <button
            className="btn-primary"
            disabled={!file}
            onClick={() => (templateId ? void run("preview") : setStep(2))}
          >
            {t("common.next")}
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="card space-y-5">
          <div className="grid md:grid-cols-3 gap-4">
            {REQUIRED_FIELDS.map((field) => columnSelect(field, true))}
            {OPTIONAL_FIELDS.map((field) => columnSelect(field, false))}
            <div>
              <label className="label">{t("import.dateFormat")}</label>
              <select className="input" dir="ltr" value={dateFormat} onChange={(e) => setDateFormat(e.target.value)}>
                <option value="%d/%m/%Y">31/12/2026</option>
                <option value="%Y-%m-%d">2026-12-31</option>
                <option value="%m/%d/%Y">12/31/2026</option>
                <option value="%d-%m-%Y">31-12-2026</option>
              </select>
            </div>
          </div>
          <div>
            <div className="label">{t("import.vatMap")}</div>
            <p className="text-xs text-slate-400 mb-2">{t("import.vatMapHint")}</p>
            <div className="space-y-2">
              {vatMap.map((entry, index) => (
                <div key={index} className="flex gap-2">
                  <input
                    className="input w-40"
                    dir="ltr"
                    value={entry.raw}
                    onChange={(e) =>
                      setVatMap((m) => m.map((x, i) => (i === index ? { ...x, raw: e.target.value } : x)))
                    }
                  />
                  <select
                    className="input w-44"
                    value={entry.category}
                    onChange={(e) =>
                      setVatMap((m) => m.map((x, i) => (i === index ? { ...x, category: e.target.value } : x)))
                    }
                  >
                    <option value="S">{t("form.vatS")}</option>
                    <option value="Z">{t("form.vatZ")}</option>
                    <option value="E">{t("form.vatE")}</option>
                    <option value="AE">{t("form.vatAE")}</option>
                  </select>
                  <button className="btn-secondary" onClick={() => setVatMap((m) => m.filter((_, i) => i !== index))}>
                    ✕
                  </button>
                </div>
              ))}
              <button className="btn-secondary" onClick={() => setVatMap((m) => [...m, { raw: "", category: "S" }])}>
                + {t("import.addVatValue")}
              </button>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => setStep(1)}>{t("import.back")}</button>
            <button className="btn-primary" disabled={busy} onClick={() => void run("preview")}>
              {t("import.preview")}
            </button>
          </div>
        </div>
      )}

      {(step === 3 || step === 4) && report && (
        <div className="space-y-4">
          <div className="card flex flex-wrap gap-5 text-sm">
            <span>{t("import.rows", { count: report.summary.rows })}</span>
            <span className="text-emerald-700 font-semibold">
              {t("import.validInvoices", { count: report.summary.valid })}
            </span>
            <span className={report.summary.invalid > 0 ? "text-rose-600 font-semibold" : "text-slate-400"}>
              {t("import.invalidInvoices", { count: report.summary.invalid })}
            </span>
            {committed && (
              <span className="text-emerald-700 font-bold">
                {t("import.created", { count: report.summary.created })}
              </span>
            )}
          </div>
          <ErrorList errors={report.file_errors} />
          {report.row_issues.map((issue) => (
            <div key={issue.row}>
              <div className="text-sm font-semibold mb-1">{t("import.rowLabel", { rows: issue.row })}</div>
              <ErrorList errors={issue.errors} />
            </div>
          ))}
          <div className="card p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {report.invoices.map((invoice) => (
                  <tr key={invoice.invoice_number} className="border-b border-slate-100 align-top">
                    <td className="table-cell font-semibold" dir="ltr">
                      {committed && invoice.invoice_id ? (
                        <Link className="text-emerald-800 hover:underline" to={`/invoices/${invoice.invoice_id}`}>
                          {invoice.invoice_number}
                        </Link>
                      ) : (
                        invoice.invoice_number
                      )}
                    </td>
                    <td className="table-cell text-slate-400">{t("import.rowLabel", { rows: invoice.rows.join(", ") })}</td>
                    <td className="table-cell">
                      {invoice.valid ? (
                        <span className="text-emerald-700">✓</span>
                      ) : (
                        <ul className="text-rose-700 space-y-1">
                          {invoice.errors.map((error, i) => (
                            <li key={i}>{localizedMessage(error, i18n.language)}</li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {step === 3 && (
            <div className="card flex flex-wrap items-end gap-3">
              <div>
                <label className="label">{t("import.saveTemplateAs")}</label>
                <input className="input w-56" value={saveAs} onChange={(e) => setSaveAs(e.target.value)} />
              </div>
              <button className="btn-secondary" onClick={() => setStep(templateId ? 1 : 2)}>
                {t("import.back")}
              </button>
              <button
                className="btn-primary"
                disabled={busy || report.summary.valid === 0}
                onClick={() => void run("commit")}
              >
                {t("import.commit", { count: report.summary.valid })}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
