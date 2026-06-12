import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api, downloadBlob } from "../api/client";
import type { Paged } from "../api/types";
import { Spinner, money } from "../components/ui";

interface ArchiveRecord {
  id: string;
  invoice_number: string;
  buyer_name: string;
  buyer_trn?: string | null;
  issue_date: string;
  total_including_vat: string;
  retention_until: string;
}

export default function ArchivePage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");

  const records = useQuery({
    queryKey: ["archive", search],
    queryFn: () =>
      api.get<Paged<ArchiveRecord>>(
        `/archive?limit=100${search ? `&search=${encodeURIComponent(search)}` : ""}`,
      ),
  });

  async function download(record: ArchiveRecord, kind: "xml" | "pdf") {
    const blob = await api.blob(`/archive/${record.id}/${kind}`);
    downloadBlob(blob, `${record.invoice_number}.${kind}`);
  }

  async function exportZip() {
    const blob = await api.blob("/archive/export");
    downloadBlob(blob, "archive.zip");
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-bold">{t("archive.title")}</h1>
          <p className="text-sm text-slate-500">{t("archive.hint")}</p>
        </div>
        <button className="btn-secondary" onClick={() => void exportZip()}>
          {t("archive.export")}
        </button>
      </div>
      <input
        className="input max-w-sm"
        placeholder={t("contacts.search")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {records.isLoading ? (
        <Spinner />
      ) : (records.data?.total ?? 0) === 0 ? (
        <div className="card text-center text-sm text-slate-500">{t("archive.empty")}</div>
      ) : (
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <th className="table-cell text-start">{t("invoices.number")}</th>
                <th className="table-cell text-start">{t("invoices.issueDate")}</th>
                <th className="table-cell text-start">{t("invoices.buyer")}</th>
                <th className="table-cell text-end">{t("invoices.total")}</th>
                <th className="table-cell text-start">{t("archive.retention")}</th>
                <th className="table-cell" />
              </tr>
            </thead>
            <tbody>
              {records.data?.items.map((record) => (
                <tr key={record.id} className="border-b border-slate-100">
                  <td className="table-cell font-semibold" dir="ltr">{record.invoice_number}</td>
                  <td className="table-cell tabular-nums" dir="ltr">{record.issue_date}</td>
                  <td className="table-cell">{record.buyer_name}</td>
                  <td className="table-cell text-end tabular-nums" dir="ltr">{money(record.total_including_vat)}</td>
                  <td className="table-cell tabular-nums" dir="ltr">{record.retention_until}</td>
                  <td className="table-cell text-end whitespace-nowrap">
                    <button className="text-emerald-700 hover:underline me-3" onClick={() => void download(record, "pdf")}>
                      PDF
                    </button>
                    <button className="text-emerald-700 hover:underline" onClick={() => void download(record, "xml")}>
                      XML
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
