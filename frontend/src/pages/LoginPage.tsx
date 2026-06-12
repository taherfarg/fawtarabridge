import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { ErrorList, errorsOf } from "../components/ui";
import { switchLanguage } from "../i18n";
import type { ErrorDetail } from "../api/types";

export default function LoginPage() {
  const { t, i18n } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<ErrorDetail[]>([]);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setErrors(errorsOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-emerald-900 p-4">
      <div className="card w-full max-w-md">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-emerald-900">{t("app.name")}</h1>
            <p className="text-sm text-slate-500 mb-6">{t("app.tagline")}</p>
          </div>
          <button
            className="text-sm text-emerald-700 underline"
            onClick={() => switchLanguage(i18n.language === "ar" ? "en" : "ar")}
          >
            {t("common.language")}
          </button>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">{t("auth.email")}</label>
            <input className="input" type="email" dir="ltr" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">{t("auth.password")}</label>
            <input className="input" type="password" dir="ltr" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <ErrorList errors={errors} />
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? t("auth.working") : t("auth.login")}
          </button>
        </form>
        <p className="mt-4 text-sm text-slate-500">
          {t("auth.noAccount")}{" "}
          <Link to="/signup" className="text-emerald-700 font-semibold">
            {t("auth.signup")}
          </Link>
        </p>
      </div>
    </div>
  );
}
