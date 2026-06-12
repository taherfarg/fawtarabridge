import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ErrorDetail, MemberOut, TenantOut } from "../api/types";
import { ErrorList, Spinner, errorsOf } from "../components/ui";
import { useAuth } from "../auth/AuthContext";

export default function SettingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user, refreshUser } = useAuth();

  const tenant = useQuery({ queryKey: ["tenant"], queryFn: () => api.get<TenantOut>("/tenants/me") });
  const members = useQuery({
    queryKey: ["members"],
    queryFn: () => api.get<MemberOut[]>("/tenants/me/members"),
    retry: false,
  });

  const [profile, setProfile] = useState({ legal_name_ar: "", legal_name_en: "", license_no: "", emirate: "", address: "" });
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileErrors, setProfileErrors] = useState<ErrorDetail[]>([]);
  useEffect(() => {
    if (tenant.data) {
      setProfile({
        legal_name_ar: tenant.data.legal_name_ar,
        legal_name_en: tenant.data.legal_name_en,
        license_no: tenant.data.license_no ?? "",
        emirate: tenant.data.emirate ?? "",
        address: tenant.data.address ?? "",
      });
    }
  }, [tenant.data]);

  const saveProfile = useMutation({
    mutationFn: () =>
      api.patch<TenantOut>("/tenants/me", {
        legal_name_ar: profile.legal_name_ar,
        legal_name_en: profile.legal_name_en,
        license_no: profile.license_no || null,
        emirate: profile.emirate || null,
        address: profile.address || null,
      }),
    onSuccess: () => {
      setProfileSaved(true);
      setProfileErrors([]);
      void queryClient.invalidateQueries({ queryKey: ["tenant"] });
    },
    onError: (err) => setProfileErrors(errorsOf(err)),
  });

  const onboardAsp = useMutation({
    mutationFn: () => api.post("/tenants/me/onboard-asp"),
    onSuccess: () => setTimeout(() => void queryClient.invalidateQueries({ queryKey: ["tenant"] }), 600),
    onError: (err) => setProfileErrors(errorsOf(err)),
  });

  const [member, setMember] = useState({ email: "", full_name: "", phone: "", password: "", role: "staff" });
  const [memberErrors, setMemberErrors] = useState<ErrorDetail[]>([]);
  const addMember = useMutation({
    mutationFn: () => api.post("/tenants/me/members", member),
    onSuccess: () => {
      setMember({ email: "", full_name: "", phone: "", password: "", role: "staff" });
      setMemberErrors([]);
      void queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (err) => setMemberErrors(errorsOf(err)),
  });

  const [otpCode, setOtpCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpErrors, setOtpErrors] = useState<ErrorDetail[]>([]);
  const requestOtp = useMutation({
    mutationFn: () => api.post("/auth/otp/request"),
    onSuccess: () => {
      setOtpSent(true);
      setOtpErrors([]);
    },
    onError: (err) => setOtpErrors(errorsOf(err)),
  });
  const verifyOtp = useMutation({
    mutationFn: () => api.post("/auth/otp/verify", { code: otpCode }),
    onSuccess: () => {
      setOtpErrors([]);
      void refreshUser();
    },
    onError: (err) => setOtpErrors(errorsOf(err)),
  });

  if (tenant.isLoading) return <Spinner />;
  const aspStatus = tenant.data?.asp_onboarding_status ?? "not_started";

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">{t("settings.title")}</h1>

      <section className="card space-y-4">
        <h2 className="font-semibold">{t("settings.company")}</h2>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="label">{t("auth.companyNameAr")}</label>
            <input className="input" dir="rtl" value={profile.legal_name_ar}
              onChange={(e) => setProfile((p) => ({ ...p, legal_name_ar: e.target.value }))} />
          </div>
          <div>
            <label className="label">{t("auth.companyNameEn")}</label>
            <input className="input" dir="ltr" value={profile.legal_name_en}
              onChange={(e) => setProfile((p) => ({ ...p, legal_name_en: e.target.value }))} />
          </div>
          <div>
            <label className="label">{t("auth.trn")}</label>
            <input className="input bg-slate-100" dir="ltr" disabled value={tenant.data?.trn ?? ""} />
          </div>
          <div>
            <label className="label">{t("settings.licenseNo")}</label>
            <input className="input" dir="ltr" value={profile.license_no}
              onChange={(e) => setProfile((p) => ({ ...p, license_no: e.target.value }))} />
          </div>
          <div>
            <label className="label">{t("auth.emirate")}</label>
            <input className="input" value={profile.emirate}
              onChange={(e) => setProfile((p) => ({ ...p, emirate: e.target.value }))} />
          </div>
          <div>
            <label className="label">{t("settings.address")}</label>
            <input className="input" value={profile.address}
              onChange={(e) => setProfile((p) => ({ ...p, address: e.target.value }))} />
          </div>
        </div>
        <ErrorList errors={profileErrors} />
        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={saveProfile.isPending} onClick={() => saveProfile.mutate()}>
            {t("settings.save")}
          </button>
          {profileSaved && <span className="text-sm text-emerald-700">{t("settings.companySaved")}</span>}
        </div>
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">{t("settings.peppol")}</h2>
        <div className="text-sm">
          {t("settings.peppolStatus")}:{" "}
          <span className="font-semibold">{t(`settings.peppolStatuses.${aspStatus}`)}</span>
        </div>
        {tenant.data?.asp_participant_id && (
          <div className="text-sm text-slate-500" dir="ltr">
            {t("settings.participantId")}: {tenant.data.asp_participant_id}
          </div>
        )}
        {(aspStatus === "not_started" || aspStatus === "failed") && (
          <button className="btn-primary" disabled={onboardAsp.isPending} onClick={() => onboardAsp.mutate()}>
            {t("settings.peppolRegister")}
          </button>
        )}
      </section>

      <section className="card space-y-3">
        <h2 className="font-semibold">{t("settings.phoneVerification")}</h2>
        <div className="text-sm">
          {user?.phone_verified ? (
            <span className="text-emerald-700 font-semibold">✓ {t("settings.phoneVerified")}</span>
          ) : (
            <span className="text-amber-600">{t("settings.phoneNotVerified")}</span>
          )}
        </div>
        {!user?.phone_verified && (
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-secondary" onClick={() => requestOtp.mutate()}>
              {t("settings.sendCode")}
            </button>
            {otpSent && (
              <>
                <input className="input w-32" dir="ltr" placeholder={t("settings.enterCode")}
                  value={otpCode} onChange={(e) => setOtpCode(e.target.value)} />
                <button className="btn-primary" onClick={() => verifyOtp.mutate()}>
                  {t("settings.verify")}
                </button>
              </>
            )}
          </div>
        )}
        {otpSent && <p className="text-xs text-slate-400">{t("settings.codeSentHint")}</p>}
        <ErrorList errors={otpErrors} />
      </section>

      {members.data && (
        <section className="card space-y-4">
          <h2 className="font-semibold">{t("settings.members")}</h2>
          <table className="w-full text-sm">
            <tbody>
              {members.data.map((m) => (
                <tr key={m.user.id} className="border-b border-slate-100">
                  <td className="table-cell">{m.user.full_name}</td>
                  <td className="table-cell" dir="ltr">{m.user.email}</td>
                  <td className="table-cell">{t(`settings.roles.${m.role}`)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid md:grid-cols-5 gap-2 items-end">
            <input className="input" placeholder={t("auth.email")} dir="ltr" value={member.email}
              onChange={(e) => setMember((m) => ({ ...m, email: e.target.value }))} />
            <input className="input" placeholder={t("auth.fullName")} value={member.full_name}
              onChange={(e) => setMember((m) => ({ ...m, full_name: e.target.value }))} />
            <input className="input" placeholder={t("auth.phone")} dir="ltr" value={member.phone}
              onChange={(e) => setMember((m) => ({ ...m, phone: e.target.value }))} />
            <input className="input" placeholder={t("auth.password")} type="password" dir="ltr" value={member.password}
              onChange={(e) => setMember((m) => ({ ...m, password: e.target.value }))} />
            <select className="input" value={member.role}
              onChange={(e) => setMember((m) => ({ ...m, role: e.target.value }))}>
              {(["accountant", "staff", "readonly"] as const).map((role) => (
                <option key={role} value={role}>{t(`settings.roles.${role}`)}</option>
              ))}
            </select>
          </div>
          <ErrorList errors={memberErrors} />
          <button className="btn-secondary" disabled={addMember.isPending} onClick={() => addMember.mutate()}>
            {t("settings.addMember")}
          </button>
        </section>
      )}

      <section className="card space-y-2">
        <h2 className="font-semibold">{t("settings.notifications")}</h2>
        <p className="text-sm text-slate-500">{t("settings.notificationsSoon")}</p>
      </section>
    </div>
  );
}
