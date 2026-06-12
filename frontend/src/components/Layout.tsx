import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { switchLanguage } from "../i18n";
import { useAuth } from "../auth/AuthContext";

const NAV = [
  { to: "/", key: "nav.dashboard", end: true },
  { to: "/invoices", key: "nav.invoices" },
  { to: "/import", key: "nav.import" },
  { to: "/contacts", key: "nav.contacts" },
  { to: "/archive", key: "nav.archive" },
  { to: "/settings", key: "nav.settings" },
];

export default function Layout() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen md:flex">
      <aside className="md:w-60 shrink-0 bg-emerald-900 text-emerald-50 flex md:flex-col md:min-h-screen">
        <div className="px-5 py-4 text-lg font-bold hidden md:block">{t("app.name")}</div>
        <nav className="flex md:flex-col gap-1 px-2 md:px-3 py-2 overflow-x-auto grow">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm whitespace-nowrap ${
                  isActive ? "bg-emerald-700 font-semibold" : "hover:bg-emerald-800"
                }`
              }
            >
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
        <div className="px-3 py-3 md:border-t border-emerald-800 flex md:flex-col gap-2 items-center md:items-stretch">
          <button
            className="rounded-lg px-3 py-1.5 text-sm hover:bg-emerald-800 text-start"
            onClick={() => switchLanguage(i18n.language === "ar" ? "en" : "ar")}
          >
            {t("common.language")}
          </button>
          <div className="text-xs opacity-70 hidden md:block truncate">{user?.email}</div>
          <button
            className="rounded-lg px-3 py-1.5 text-sm hover:bg-emerald-800 text-start"
            onClick={logout}
          >
            {t("nav.logout")}
          </button>
        </div>
      </aside>
      <main className="grow p-4 md:p-8 max-w-6xl w-full mx-auto">
        <Outlet />
      </main>
    </div>
  );
}
