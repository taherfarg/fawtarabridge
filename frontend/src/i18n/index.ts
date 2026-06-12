import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./ar.json";
import en from "./en.json";

const stored = localStorage.getItem("fawtara.lang");
const initial = stored === "en" ? "en" : "ar"; // Arabic is the default

void i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: initial,
  fallbackLng: "ar",
  interpolation: { escapeValue: false },
});

export function applyDirection(lang: string): void {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

export function switchLanguage(lang: "ar" | "en"): void {
  void i18n.changeLanguage(lang);
  localStorage.setItem("fawtara.lang", lang);
  applyDirection(lang);
}

applyDirection(initial);

export default i18n;
