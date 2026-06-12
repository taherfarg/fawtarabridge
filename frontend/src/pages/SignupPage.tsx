import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthContext";
import { ErrorList, errorsOf } from "../components/ui";
import type { ErrorDetail } from "../api/types";

const EMIRATES = ["Abu Dhabi", "Dubai", "Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"];

export default function SignupPage() {
  const { t } = useTranslation();
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    email: "",
    password: "",
    full_name: "",
    phone: "",
    legal_name_ar: "",
    legal_name_en: "",
    trn: "",
    emirate: "Dubai",
    revenue_band: "lt_50m",
  });
  const [errors, setErrors] = useState<ErrorDetail[]>([]);
  const [busy, setBusy] = useState(false);

  function field(key: keyof typeof form) {
    return {
      value: form[key],
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
        setForm((f) => ({ ...f, [key]: e.target.value })),
    };
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await signup({
        email: form.email,
        password: form.password,
        full_name: form.full_name,
        phone: form.phone,
        company: {
          legal_name_ar: form.legal_name_ar,
          legal_name_en: form.legal_name_en,
          trn: form.trn,
          emirate: form.emirate,
          revenue_band: form.revenue_band,
        },
      });
      navigate("/");
    } catch (err) {
      setErrors(errorsOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-emerald-900 p-4">
      <div className="card w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-emerald-900 mb-6">{t("auth.signup")}</h1>
        <form onSubmit={submit} className="grid md:grid-cols-2 gap-4">
          <div>
            <label className="label">{t("auth.fullName")}</label>
            <input className="input" required {...field("full_name")} />
          </div>
          <div>
            <label className="label">{t("auth.phone")}</label>
            <input className="input" dir="ltr" placeholder="+9715xxxxxxxx" required {...field("phone")} />
          </div>
          <div>
            <label className="label">{t("auth.email")}</label>
            <input className="input" type="email" dir="ltr" required {...field("email")} />
          </div>
          <div>
            <label className="label">{t("auth.password")}</label>
            <input className="input" type="password" dir="ltr" required minLength={8} {...field("password")} />
          </div>
          <div>
            <label className="label">{t("auth.companyNameAr")}</label>
            <input className="input" dir="rtl" required {...field("legal_name_ar")} />
          </div>
          <div>
            <label className="label">{t("auth.companyNameEn")}</label>
            <input className="input" dir="ltr" required {...field("legal_name_en")} />
          </div>
          <div>
            <label className="label">{t("auth.trn")}</label>
            <input className="input" dir="ltr" required maxLength={15} placeholder="100XXXXXXXXXXXX" {...field("trn")} />
          </div>
          <div>
            <label className="label">{t("auth.emirate")}</label>
            <select className="input" {...field("emirate")}>
              {EMIRATES.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="label">{t("auth.revenueBand")}</label>
            <select className="input" {...field("revenue_band")}>
              <option value="lt_50m">{t("auth.revenueBandLow")}</option>
              <option value="gte_50m">{t("auth.revenueBandHigh")}</option>
              <option value="unknown">{t("auth.revenueBandUnknown")}</option>
            </select>
          </div>
          <div className="md:col-span-2 space-y-3">
            <ErrorList errors={errors} />
            <button className="btn-primary w-full" disabled={busy}>
              {busy ? t("auth.working") : t("auth.signup")}
            </button>
            <p className="text-sm text-slate-500">
              {t("auth.haveAccount")}{" "}
              <Link to="/login" className="text-emerald-700 font-semibold">{t("auth.login")}</Link>
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
