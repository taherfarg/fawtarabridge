import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { InvoiceOut, Paged } from "../api/types";
import { Spinner, StatusBadge, money } from "../components/ui";

const STATUSES = ["DRAFT", "VALIDATED", "QUEUED", "SENT", "ACCEPTED", "REJECTED", "ERROR"];
const PAGE_SIZE = 25;

export default function InvoicesPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const buyer = params.get("buyer") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const page = Number(params.get("page") ?? "0");

  const query = new URLSearchParams();
  if (status) query.set("status", status);
  if (buyer) query.set("buyer", buyer);
  if (from) query.set("from", from);
  if (to) query.set("to", to);
  query.set("limit", String(PAGE_SIZE));
  query.set("offset", String(page * PAGE_SIZE));

  const invoices = useQuery({
    queryKey: ["invoices", query.toString()],
    queryFn: () => api.get<Paged<InvoiceOut>>(`/invoices?${query}`),
  });
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkResult, setBulkResult] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function runBulk(action: "validate" | "send") {
    const result = await api.post<{ succeeded: number; failed: number }>("/invoices/bulk", {
      action,
      ids: [...selected],
    });
    setBulkResult(t("invoices.bulkDone", { ok: result.succeeded, failed: result.failed }));
    setSelected(new Set());
    void queryClient.invalidateQueries({ queryKey: ["invoices"] });
  }

  function setFilter(key: string, value: string) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      next.delete("page");
      return next;
    });
  }

  const total = invoices.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold">{t("invoices.title")}</h1>
        <Link to="/invoices/new" className="btn-primary">
          {t("invoices.create")}
        </Link>
      </div>

      <div className="card flex flex-wrap gap-3 items-end">
        <div>
          <label className="label">{t("invoices.status")}</label>
          <select className="input w-44" value={status} onChange={(e) => setFilter("status", e.target.value)}>
            <option value="">{t("invoices.allStatuses")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{t(`statuses.${s}`)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">{t("invoices.buyer")}</label>
          <input
            className="input w-52"
            placeholder={t("invoices.searchBuyer")}
            defaultValue={buyer}
            onKeyDown={(e) => e.key === "Enter" && setFilter("buyer", e.currentTarget.value)}
            onBlur={(e) => setFilter("buyer", e.target.value)}
          />
        </div>
        <div>
          <label className="label">{t("invoices.from")}</label>
          <input className="input" type="date" value={from} onChange={(e) => setFilter("from", e.target.value)} />
        </div>
        <div>
          <label className="label">{t("invoices.to")}</label>
          <input className="input" type="date" value={to} onChange={(e) => setFilter("to", e.target.value)} />
        </div>
      </div>

      {invoices.isLoading ? (
        <Spinner />
      ) : total === 0 ? (
        <div className="card text-center text-slate-500 text-sm">{t("invoices.empty")}</div>
      ) : (
        <div className="card overflow-x-auto p-0">
          {(selected.size > 0 || bulkResult) && (
            <div className="flex items-center gap-3 px-3 py-2 border-b border-slate-200 bg-slate-50 text-sm">
              {selected.size > 0 && (
                <>
                  <span>{t("invoices.selected", { count: selected.size })}</span>
                  <button className="btn-secondary" onClick={() => void runBulk("validate")}>
                    {t("invoices.validate")}
                  </button>
                  <button className="btn-primary" onClick={() => void runBulk("send")}>
                    {t("invoices.send")}
                  </button>
                </>
              )}
              {bulkResult && <span className="text-emerald-700">{bulkResult}</span>}
            </div>
          )}
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 text-start text-xs uppercase text-slate-500">
                <th className="table-cell w-8" />
                <th className="table-cell text-start">{t("invoices.number")}</th>
                <th className="table-cell text-start">{t("invoices.issueDate")}</th>
                <th className="table-cell text-start">{t("invoices.buyer")}</th>
                <th className="table-cell text-end">{t("invoices.total")}</th>
                <th className="table-cell text-start">{t("invoices.status")}</th>
              </tr>
            </thead>
            <tbody>
              {invoices.data?.items.map((invoice) => (
                <tr key={invoice.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="table-cell">
                    <input
                      type="checkbox"
                      checked={selected.has(invoice.id)}
                      onChange={() => toggle(invoice.id)}
                    />
                  </td>
                  <td className="table-cell">
                    <Link to={`/invoices/${invoice.id}`} className="font-semibold text-emerald-800 hover:underline">
                      {invoice.invoice_number}
                    </Link>
                    {invoice.duplicate_warning && (
                      <span className="ms-2 text-xs text-amber-600" title={t("invoices.duplicateFlag")}>⚠</span>
                    )}
                  </td>
                  <td className="table-cell tabular-nums" dir="ltr">{invoice.issue_date}</td>
                  <td className="table-cell">{invoice.buyer_name}</td>
                  <td className="table-cell text-end tabular-nums" dir="ltr">{money(invoice.total_including_vat)}</td>
                  <td className="table-cell"><StatusBadge status={invoice.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="flex items-center gap-3 text-sm">
          <button className="btn-secondary" disabled={page <= 0} onClick={() => setFilter("page", String(page - 1))}>
            {t("common.previous")}
          </button>
          <span>
            {page + 1} {t("common.of")} {pages}
          </span>
          <button className="btn-secondary" disabled={page >= pages - 1} onClick={() => setFilter("page", String(page + 1))}>
            {t("common.next")}
          </button>
        </div>
      )}
    </div>
  );
}
