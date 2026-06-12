import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api, downloadBlob } from "../api/client";
import type { AuditEventOut, InvoiceDetailOut, ValidationReport } from "../api/types";
import { ErrorList, Spinner, StatusBadge, errorsOf, money } from "../components/ui";
import { useState } from "react";
import type { ErrorDetail } from "../api/types";

const EDITABLE = ["DRAFT", "VALIDATED", "REJECTED", "ERROR"];

export default function InvoiceDetailPage() {
  const { t, i18n } = useTranslation();
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [actionErrors, setActionErrors] = useState<ErrorDetail[]>([]);

  const invoice = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => api.get<InvoiceDetailOut>(`/invoices/${id}`),
  });
  const audit = useQuery({
    queryKey: ["audit", id],
    queryFn: () => api.get<AuditEventOut[]>(`/invoices/${id}/audit`),
  });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["invoice", id] });
    void queryClient.invalidateQueries({ queryKey: ["audit", id] });
  }

  const validate = useMutation({
    mutationFn: () => api.post<ValidationReport>(`/invoices/${id}/validate`),
    onSuccess: () => {
      setActionErrors([]);
      refresh();
    },
    onError: (err) => setActionErrors(errorsOf(err)),
  });
  const send = useMutation({
    mutationFn: (resend: boolean) => api.post(`/invoices/${id}/${resend ? "resend" : "send"}`),
    onSuccess: () => {
      setActionErrors([]);
      setTimeout(refresh, 400); // worker runs async; give it a beat
      refresh();
    },
    onError: (err) => setActionErrors(errorsOf(err)),
  });

  if (invoice.isLoading) return <Spinner />;
  const data = invoice.data;
  if (!data) return null;
  const canonical = data.canonical;
  const transmission = data.latest_transmission;

  async function download(kind: "xml" | "pdf") {
    try {
      const blob = await api.blob(`/invoices/${id}/${kind}`);
      downloadBlob(blob, `${data!.invoice_number}.${kind}`);
    } catch (err) {
      setActionErrors(errorsOf(err));
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold" dir="ltr">{data.invoice_number}</h1>
          <StatusBadge status={data.status} />
          {data.duplicate_warning && <span className="text-amber-600 text-sm">⚠ {t("invoices.duplicateFlag")}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          {EDITABLE.includes(data.status) && (
            <Link className="btn-secondary" to={`/invoices/${id}/edit`}>{t("invoices.edit")}</Link>
          )}
          {data.status === "DRAFT" && (
            <button className="btn-secondary" onClick={() => validate.mutate()} disabled={validate.isPending}>
              {t("invoices.validate")}
            </button>
          )}
          {data.status === "VALIDATED" && (
            <button className="btn-primary" onClick={() => send.mutate(false)} disabled={send.isPending}>
              {t("invoices.send")}
            </button>
          )}
          {(data.status === "REJECTED" || data.status === "ERROR") && (
            <button className="btn-primary" onClick={() => send.mutate(true)} disabled={send.isPending}>
              {t("invoices.resend")}
            </button>
          )}
          <button className="btn-secondary" onClick={() => download("pdf")}>{t("invoices.downloadPdf")}</button>
          <button className="btn-secondary" onClick={() => download("xml")}>{t("invoices.downloadXml")}</button>
        </div>
      </div>

      <ErrorList errors={actionErrors} />
      {transmission?.rejection && (
        <div>
          <h2 className="font-semibold text-sm mb-1">{t("invoices.rejectionReason")}</h2>
          <ErrorList errors={[transmission.rejection]} />
        </div>
      )}
      {transmission?.last_error && transmission.status !== "rejected" && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-900">
          {t("invoices.transmissionError")}: <span dir="ltr">{transmission.last_error}</span>
        </div>
      )}
      {data.errors.length > 0 && (
        <div>
          <h2 className="font-semibold text-sm mb-1">{t("invoices.validationErrors")}</h2>
          <ErrorList errors={data.errors} />
        </div>
      )}
      {data.warnings.length > 0 && <ErrorList errors={data.warnings} tone="warning" />}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card text-sm space-y-1">
          <h2 className="font-semibold mb-2">{t("invoices.supplier")}</h2>
          <div>{i18n.language === "ar" ? canonical.supplier.name_ar || canonical.supplier.name : canonical.supplier.name}</div>
          <div className="text-slate-500" dir="ltr">TRN: {canonical.supplier.trn}</div>
        </div>
        <div className="card text-sm space-y-1">
          <h2 className="font-semibold mb-2">{t("invoices.buyer")}</h2>
          <div>{i18n.language === "ar" ? canonical.buyer.name_ar || canonical.buyer.name : canonical.buyer.name}</div>
          <div className="text-slate-500" dir="ltr">TRN: {canonical.buyer.trn ?? "—"}</div>
          <div className="text-slate-500">
            {t("invoices.issueDate")}: <span dir="ltr">{canonical.issue_date}</span>
            {canonical.due_date && (
              <>
                {" · "}
                {t("invoices.dueDate")}: <span dir="ltr">{canonical.due_date}</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="card p-0 overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <th className="table-cell text-start">#</th>
              <th className="table-cell text-start">{t("form.description")}</th>
              <th className="table-cell text-end">{t("form.qty")}</th>
              <th className="table-cell text-end">{t("form.unitPrice")}</th>
              <th className="table-cell text-end">{t("form.discount")}</th>
              <th className="table-cell text-center">{t("form.vat")}</th>
            </tr>
          </thead>
          <tbody>
            {canonical.lines.map((line) => (
              <tr key={line.line_id} className="border-b border-slate-100">
                <td className="table-cell">{line.line_id}</td>
                <td className="table-cell">
                  {i18n.language === "ar" && line.description_ar ? line.description_ar : line.description}
                </td>
                <td className="table-cell text-end tabular-nums" dir="ltr">{line.quantity}</td>
                <td className="table-cell text-end tabular-nums" dir="ltr">{money(line.unit_price)}</td>
                <td className="table-cell text-end tabular-nums" dir="ltr">{money(line.discount_amount ?? 0)}</td>
                <td className="table-cell text-center" dir="ltr">{line.vat_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-4 py-3 text-end font-semibold">
          {t("invoices.total")}: <span dir="ltr">AED {money(data.total_including_vat)}</span>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-3">{t("invoices.timeline")}</h2>
        {audit.isLoading ? (
          <Spinner />
        ) : (
          <ol className="space-y-2 text-sm">
            {audit.data?.map((event) => (
              <li key={event.id} className="flex flex-wrap items-baseline gap-2">
                <span className="text-slate-400 text-xs tabular-nums" dir="ltr">
                  {new Date(event.created_at).toLocaleString(i18n.language === "ar" ? "ar-AE" : "en-GB")}
                </span>
                <span>{t(`invoices.audit.${event.action}`, event.action)}</span>
                {event.action === "invoice.status_changed" && (
                  <span className="text-slate-500" dir="ltr">
                    {String(event.before?.status)} → {String(event.after?.status)}
                  </span>
                )}
                <span className="text-xs text-slate-400">({event.actor_type})</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
