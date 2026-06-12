import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api/client";
import type { ContactOut, ErrorDetail, Paged } from "../api/types";
import { ErrorList, Spinner, errorsOf } from "../components/ui";

const EMPTY = { name_en: "", name_ar: "", trn: "", email: "", phone: "", city: "", emirate: "" };

export default function ContactsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<ContactOut | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState<ErrorDetail[]>([]);

  const contacts = useQuery({
    queryKey: ["contacts", search],
    queryFn: () => api.get<Paged<ContactOut>>(`/contacts?limit=100${search ? `&search=${encodeURIComponent(search)}` : ""}`),
  });

  function open(contact: ContactOut | "new") {
    setErrors([]);
    setEditing(contact);
    setForm(
      contact === "new"
        ? EMPTY
        : {
            name_en: contact.name_en,
            name_ar: contact.name_ar ?? "",
            trn: contact.trn ?? "",
            email: contact.email ?? "",
            phone: contact.phone ?? "",
            city: contact.city ?? "",
            emirate: contact.emirate ?? "",
          },
    );
  }

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name_en: form.name_en,
        name_ar: form.name_ar || null,
        trn: form.trn || null,
        email: form.email || null,
        phone: form.phone || null,
        city: form.city || null,
        emirate: form.emirate || null,
      };
      return editing === "new"
        ? api.post("/contacts", payload)
        : api.put(`/contacts/${(editing as ContactOut).id}`, payload);
    },
    onSuccess: () => {
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (err) => setErrors(errorsOf(err)),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/contacts/${id}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["contacts"] }),
  });

  function field(key: keyof typeof EMPTY, dir?: string) {
    return (
      <input
        className="input"
        dir={dir}
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-2xl font-bold">{t("contacts.title")}</h1>
        <button className="btn-primary" onClick={() => open("new")}>
          {t("contacts.add")}
        </button>
      </div>
      <input
        className="input max-w-sm"
        placeholder={t("contacts.search")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {contacts.isLoading ? (
        <Spinner />
      ) : (contacts.data?.total ?? 0) === 0 ? (
        <div className="card text-center text-sm text-slate-500">{t("contacts.empty")}</div>
      ) : (
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <th className="table-cell text-start">{t("contacts.nameEn")}</th>
                <th className="table-cell text-start">{t("contacts.nameAr")}</th>
                <th className="table-cell text-start">{t("contacts.trn")}</th>
                <th className="table-cell text-start">{t("contacts.emirate")}</th>
                <th className="table-cell" />
              </tr>
            </thead>
            <tbody>
              {contacts.data?.items.map((contact) => (
                <tr key={contact.id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="table-cell font-medium">{contact.name_en}</td>
                  <td className="table-cell" dir="rtl">{contact.name_ar}</td>
                  <td className="table-cell tabular-nums" dir="ltr">{contact.trn}</td>
                  <td className="table-cell">{contact.emirate}</td>
                  <td className="table-cell text-end whitespace-nowrap">
                    <button className="text-emerald-700 hover:underline me-3" onClick={() => open(contact)}>
                      {t("contacts.edit")}
                    </button>
                    <button
                      className="text-rose-600 hover:underline"
                      onClick={() => window.confirm(t("common.confirmDelete")) && remove.mutate(contact.id)}
                    >
                      {t("contacts.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-10">
          <div className="card w-full max-w-lg space-y-4">
            <h2 className="text-lg font-bold">
              {editing === "new" ? t("contacts.add") : t("contacts.edit")}
            </h2>
            <div className="grid md:grid-cols-2 gap-3">
              <div><label className="label">{t("contacts.nameEn")}</label>{field("name_en")}</div>
              <div><label className="label">{t("contacts.nameAr")}</label>{field("name_ar", "rtl")}</div>
              <div><label className="label">{t("contacts.trn")}</label>{field("trn", "ltr")}</div>
              <div><label className="label">{t("contacts.email")}</label>{field("email", "ltr")}</div>
              <div><label className="label">{t("contacts.phone")}</label>{field("phone", "ltr")}</div>
              <div><label className="label">{t("contacts.city")}</label>{field("city")}</div>
              <div><label className="label">{t("contacts.emirate")}</label>{field("emirate")}</div>
            </div>
            <ErrorList errors={errors} />
            <div className="flex gap-2 justify-end">
              <button className="btn-secondary" onClick={() => setEditing(null)}>
                {t("common.cancel")}
              </button>
              <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>
                {t("contacts.save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
