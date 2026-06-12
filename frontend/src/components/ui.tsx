import { useTranslation } from "react-i18next";
import type { ErrorDetail, InvoiceStatus } from "../api/types";
import { ApiError } from "../api/client";

const STATUS_STYLES: Record<InvoiceStatus, string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  VALIDATED: "bg-sky-100 text-sky-800",
  QUEUED: "bg-amber-100 text-amber-800",
  SENT: "bg-indigo-100 text-indigo-800",
  ACCEPTED: "bg-emerald-100 text-emerald-800",
  REJECTED: "bg-rose-100 text-rose-800",
  ERROR: "bg-orange-100 text-orange-800",
};

export function StatusBadge({ status }: { status: InvoiceStatus }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[status] ?? "bg-slate-100"}`}
    >
      {t(`statuses.${status}`)}
    </span>
  );
}

export function localizedMessage(error: ErrorDetail, lang: string): string {
  return lang === "ar" ? error.message_ar : error.message_en;
}

export function localizedSuggestion(error: ErrorDetail, lang: string): string | null | undefined {
  return lang === "ar" ? error.suggestion_ar : error.suggestion_en;
}

export function ErrorList({
  errors,
  tone = "error",
}: {
  errors: ErrorDetail[];
  tone?: "error" | "warning";
}) {
  const { t, i18n } = useTranslation();
  if (errors.length === 0) return null;
  const toneClass =
    tone === "error"
      ? "border-rose-200 bg-rose-50 text-rose-900"
      : "border-amber-200 bg-amber-50 text-amber-900";
  return (
    <ul className={`rounded-lg border px-4 py-3 text-sm space-y-2 ${toneClass}`}>
      {errors.map((error, index) => {
        const suggestion = localizedSuggestion(error, i18n.language);
        return (
          <li key={`${error.code}-${error.field ?? ""}-${index}`}>
            <span className="font-medium">{localizedMessage(error, i18n.language)}</span>
            {error.field ? <span className="opacity-60"> ({error.field})</span> : null}
            {suggestion ? (
              <div className="opacity-80">
                {t("common.suggestion")}: {suggestion}
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function errorsOf(err: unknown): ErrorDetail[] {
  if (err instanceof ApiError) return err.errors;
  return [
    {
      code: "client.error",
      message_en: err instanceof Error ? err.message : "Unexpected error",
      message_ar: "حدث خطأ غير متوقع",
    },
  ];
}

export function Spinner() {
  const { t } = useTranslation();
  return <div className="py-10 text-center text-sm text-slate-500">{t("common.loading")}</div>;
}

export function money(value: string | number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  return numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
