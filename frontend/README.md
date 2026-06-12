# FawtaraBridge Frontend

React 18 + Vite + TypeScript + TailwindCSS v4. Arabic-first with full RTL;
language toggle to English (react-i18next, `dir` switches with the language).

```bash
npm install
npm run dev      # http://localhost:5173 — proxies /api to localhost:8000
npm run build    # type-check (tsc -b) + production build
npm test         # vitest
```

Screens: login/signup, dashboard (compliance health, penalty risk, deadline
banner by revenue band, onboarding checklist, pending actions), invoice list +
detail (audit timeline, XML/PDF download, validate/send/fix-and-resend), invoice
form, CSV/Excel import wizard (upload → map → preview → commit, saved mapping
templates), contacts, archive (search + ZIP export), settings (company profile,
Peppol onboarding, phone OTP, team members).

API errors arrive bilingual from the backend (`message_ar`/`message_en`) and are
rendered in the active language — the frontend never re-translates error codes.

Demo data: `uv run python scripts/seed_demo.py` in `backend/`, then sign in as
`demo@fawtarabridge.ae` / `Demo12345!`.
