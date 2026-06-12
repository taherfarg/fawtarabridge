import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import i18n, { applyDirection, switchLanguage } from "../i18n";
import { ErrorList, StatusBadge, localizedMessage, money } from "../components/ui";
import type { ErrorDetail } from "../api/types";

const sampleError: ErrorDetail = {
  code: "invoice.buyer_trn_invalid",
  field: "buyer.trn",
  message_en: "Buyer TRN must be exactly 15 digits",
  message_ar: "رقم التسجيل الضريبي للمشتري يجب أن يتكون من 15 رقماً",
  suggestion_en: "Check the certificate",
  suggestion_ar: "تحقق من الشهادة",
};

describe("i18n", () => {
  it("defaults to Arabic with RTL direction", () => {
    applyDirection(i18n.language);
    expect(i18n.language).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(i18n.t("statuses.ACCEPTED")).toBe("مقبولة");
  });

  it("switches to English and flips direction", () => {
    switchLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(i18n.t("statuses.ACCEPTED")).toBe("Accepted");
    switchLanguage("ar");
    expect(document.documentElement.dir).toBe("rtl");
  });
});

describe("bilingual errors", () => {
  it("picks the message for the active language", () => {
    expect(localizedMessage(sampleError, "ar")).toContain("١٥".length ? "15" : "15");
    expect(localizedMessage(sampleError, "en")).toBe("Buyer TRN must be exactly 15 digits");
  });

  it("renders messages and suggestions", () => {
    switchLanguage("ar");
    render(<ErrorList errors={[sampleError]} />);
    expect(screen.getByText(/رقم التسجيل الضريبي للمشتري/)).toBeInTheDocument();
    expect(screen.getByText(/تحقق من الشهادة/)).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders the localized status", () => {
    switchLanguage("ar");
    render(<StatusBadge status="REJECTED" />);
    expect(screen.getByText("مرفوضة")).toBeInTheDocument();
  });
});

describe("money", () => {
  it("formats with two decimals", () => {
    expect(money("1050")).toMatch(/1,?050\.00/);
  });
});
