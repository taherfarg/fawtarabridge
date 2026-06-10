# Golden-file test suite (PINT-AE engine)

- `inputs/valid_*.json` — canonical invoices that must validate cleanly; their
  exact serialized XML is locked in `expected/<name>.xml` and must also pass the
  vendored OASIS UBL 2.1 XSD.
- `inputs/err_*.json` — one fixture per major error class; the exact bilingual
  error list is locked in `expected/<name>.errors.json`.

These files are the engine's behavioural contract. CI fails if any of them drift.

When the official MoF PINT-AE spec or sample files dictate a change (see the
`# SPEC-CHECK:` markers in `app/pintae/`), update the engine, run

```bash
uv run python scripts/regen_golden.py
```

review the diff line by line, and commit the change together with the spec
reference that justifies it.
