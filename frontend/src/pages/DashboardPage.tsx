import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ComplianceSummary, ContactOut, Paged, TenantOut } from "../api/types";
import { Spinner, StatusBadge, money } from "../components/ui";
import { useAuth } from "../auth/AuthContext";

const DEADLINES = { gte_50m: "2027-01-01", lt_50m: "2027-07-01", unknown: "2027-07-01" } as const;

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => api.get<ComplianceSummary>("/compliance/summary"),
  });
  const tenant = useQuery({ queryKey: ["tenant"], queryFn: () => api.get<TenantOut>("/tenants/me") });
  const contacts = useQuery({
    queryKey: ["contacts", "count"],
    queryFn: () => api.get<Paged<ContactOut>>("/contacts?limit=1"),
  });

  if (summary.isLoading || tenant.isLoading) return <Spinner />;
  if (!summary.data || !tenant.data) return null;

  const counts = summary.data.counts;
  const submitted = counts.ACCEPTED + counts.REJECTED + counts.ERROR;
  const health = submitted === 0 ? null : Math.round((100 * counts.ACCEPTED) / submitted);
  const deadline = new Date(DEADLINES[tenant.data.revenue_band]);
  const daysLeft = Math.max(0, Math.ceil((deadline.getTime() - Date.now()) / 86_400_000));
  const totalInvoices = summary.data.total_invoices;

  const checklist: { key: string; done: boolean; to: string }[] = [
    { key: "checkProfile", done: Boolean(tenant.data.trn), to: "/settings" },
    { key: "checkPhone", done: Boolean(user?.phone_verified), to: "/settings" },
    { key: "checkAsp", done: tenant.data.asp_onboarding_status === "registered", to: "/settings" },
    { key: "checkContact", done: (contacts.data?.total ?? 0) > 0, to: "/contacts" },
    { key: "checkInvoice", done: totalInvoices > 0, to: "/invoices/new" },
    { key: "checkAccepted", done: counts.ACCEPTED > 0, to: "/invoices" },
  ];
  const doneCount = checklist.filter((c) => c.done).length;

  const actions = [
    { key: "actionDrafts", count: counts.DRAFT, to: "/invoices?status=DRAFT" },
    { key: "actionRejected", count: counts.REJECTED, to: "/invoices?status=REJECTED" },
    { key: "actionErrors", count: counts.ERROR, to: "/invoices?status=ERROR" },
    { key: "actionSent", count: counts.SENT, to: "/invoices?status=SENT" },
  ].filter((a) => a.count > 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("dashboard.title")}</h1>

      <div className="rounded-xl bg-emerald-800 text-emerald-50 px-5 py-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-semibold">{t("dashboard.deadlineTitle")}</div>
          <div className="text-sm opacity-90">
            {t(tenant.data.revenue_band === "gte_50m" ? "dashboard.deadlineLarge" : "dashboard.deadlineSme")}
          </div>
        </div>
        <div className="text-2xl font-bold">{t("dashboard.deadlineDays", { count: daysLeft })}</div>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-sm text-slate-500">{t("dashboard.health")}</div>
          <div className={`text-4xl font-bold ${health === null ? "text-slate-400" : health >= 90 ? "text-emerald-700" : health >= 60 ? "text-amber-600" : "text-rose-600"}`}>
            {health === null ? "—" : `${health}%`}
          </div>
          <div className="text-xs text-slate-400 mt-1">{t("dashboard.healthHint")}</div>
        </div>
        <div className="card">
          <div className="text-sm text-slate-500">{t("dashboard.penaltyRisk")}</div>
          <div className={`text-4xl font-bold ${summary.data.penalty_risk_aed > 0 ? "text-rose-600" : "text-emerald-700"}`}>
            AED {money(summary.data.penalty_risk_aed)}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            {t("dashboard.penaltyHint", {
              count: summary.data.unsent_past_due,
              cap: summary.data.penalty_cap_aed.toLocaleString(),
            })}
          </div>
        </div>
        <div className="card">
          <div className="text-sm text-slate-500">{t("dashboard.acceptedTotal")}</div>
          <div className="text-4xl font-bold text-slate-800">AED {money(summary.data.accepted_total_aed)}</div>
          <div className="text-xs text-slate-400 mt-1">
            {t("dashboard.invoicesThisMonth")}: {totalInvoices}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card">
          <h2 className="font-semibold mb-3">{t("dashboard.pendingActions")}</h2>
          {actions.length === 0 ? (
            <p className="text-sm text-slate-500">{t("dashboard.noPendingActions")}</p>
          ) : (
            <ul className="space-y-2">
              {actions.map((action) => (
                <li key={action.key}>
                  <Link to={action.to} className="text-sm text-emerald-800 hover:underline">
                    • {t(`dashboard.${action.key}`, { count: action.count })}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <h2 className="font-semibold mt-5 mb-2">{t("dashboard.statusBreakdown")}</h2>
          <div className="flex flex-wrap gap-2">
            {(Object.entries(counts) as [keyof typeof counts, number][])
              .filter(([, count]) => count > 0)
              .map(([status, count]) => (
                <Link key={status} to={`/invoices?status=${status}`} className="flex items-center gap-1.5">
                  <StatusBadge status={status} />
                  <span className="text-sm text-slate-600">{count}</span>
                </Link>
              ))}
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">{t("dashboard.checklist")}</h2>
            <span className="text-sm text-slate-500">
              {doneCount} {t("common.of")} {checklist.length}
            </span>
          </div>
          <div className="h-2 rounded-full bg-slate-100 mb-4">
            <div
              className="h-2 rounded-full bg-emerald-600 transition-all"
              style={{ width: `${(100 * doneCount) / checklist.length}%` }}
            />
          </div>
          <ul className="space-y-2">
            {checklist.map((item) => (
              <li key={item.key} className="flex items-center gap-2 text-sm">
                <span className={item.done ? "text-emerald-600" : "text-slate-300"}>
                  {item.done ? "✓" : "○"}
                </span>
                {item.done ? (
                  <span className="text-slate-400 line-through">{t(`dashboard.${item.key}`)}</span>
                ) : (
                  <Link to={item.to} className="text-emerald-800 hover:underline">
                    {t(`dashboard.${item.key}`)}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
