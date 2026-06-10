"""Regenerate golden outputs from the fixture inputs.

Usage:  uv run python scripts/regen_golden.py

For every tests/golden/inputs/valid_*.json it writes expected/<name>.xml; for every
err_*.json it writes expected/<name>.errors.json. ALWAYS review the diff before
committing — golden files are the spec contract, regeneration is not a fix.
"""

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.pintae import CanonicalInvoice, get_engine  # noqa: E402

GOLDEN = BACKEND / "tests" / "golden"
INPUTS = GOLDEN / "inputs"
EXPECTED = GOLDEN / "expected"


def main() -> None:
    EXPECTED.mkdir(parents=True, exist_ok=True)
    engine = get_engine("pint-ae-1.0")

    for path in sorted(INPUTS.glob("valid_*.json")):
        invoice = CanonicalInvoice.model_validate_json(path.read_text(encoding="utf-8"))
        errors = engine.validate(invoice)
        if errors:
            raise SystemExit(f"{path.name}: 'valid' fixture has errors: {[e.code for e in errors]}")
        out = EXPECTED / f"{path.stem}.xml"
        out.write_bytes(engine.serialize(invoice))
        print(f"wrote {out.relative_to(GOLDEN)}")

    for path in sorted(INPUTS.glob("err_*.json")):
        invoice = CanonicalInvoice.model_validate_json(path.read_text(encoding="utf-8"))
        errors = engine.validate(invoice)
        if not errors:
            raise SystemExit(f"{path.name}: 'err' fixture produced no errors")
        out = EXPECTED / f"{path.stem}.errors.json"
        payload = json.dumps([e.model_dump() for e in errors], ensure_ascii=False, indent=2)
        out.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {out.relative_to(GOLDEN)} ({len(errors)} errors)")


if __name__ == "__main__":
    main()
