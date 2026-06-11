"""Seed a demo tenant with 30 realistic invoices across all lifecycle statuses.

Usage:  uv run python scripts/seed_demo.py     (db container must be running)

Login afterwards: demo@fawtarabridge.ae / Demo12345!
Idempotent: exits if the demo tenant already exists. Works without a Celery
worker (transmissions are executed inline).
"""

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.session import get_sessionmaker, set_rls_context  # noqa: E402
from app.models import Contact, Tenant  # noqa: E402
from app.repositories.contacts import ContactRepository  # noqa: E402
from app.repositories.invoices import InvoiceRepository  # noqa: E402
from app.schemas.auth import SignupIn  # noqa: E402
from app.schemas.invoice import BuyerIn, InvoiceCreateIn, InvoiceLineIn  # noqa: E402
from app.services import auth_service, invoice_service, transmission_service  # noqa: E402
from app.services.otp import ConsoleOTPProvider  # noqa: E402

DEMO_TRN = "100000000000003"
DEMO_EMAIL = "demo@fawtarabridge.ae"

# Buyer TRN suffixes drive the mock ASP (see app/asp/mock.py).
ACCEPT = "100765432100002"
REJECT_A = "100765432100099"
REJECT_B = "100765432100098"
PERMANENT = "100765432100096"
PROCESSING = "100765432100094"

CONTACTS = [
    ("Gulf Builders LLC", "بناة الخليج ذ.م.م", ACCEPT, "Abu Dhabi"),
    ("Falcon Insurance Brokers", "فالكون لوساطة التأمين", "100888999600002", "Dubai"),
    ("Oasis Manufacturing LLC", "واحة الصناعات ذ.م.م", "100111222300009", "Ajman"),
    ("Doha Foods Trading", "الدوحة للمواد الغذائية", "100123987600002", "Sharjah"),
    ("Marina Heights Properties", "مرتفعات المارينا العقارية", "100444555600002", "Dubai"),
    ("Precision Repairs LLC", "الدقة للتصليحات ذ.م.م", "100555666700004", "Al Ain"),
]

ITEMS = [
    ("Steel pipes 2-inch", "أنابيب فولاذية 2 إنش", "85.50"),
    ("Cement bags 50kg", "أكياس إسمنت 50 كجم", "18.75"),
    ("Office desks (oak)", "مكاتب خشب البلوط", "450.00"),
    ("IT consulting (hourly)", "استشارات تقنية بالساعة", "320.00"),
    ("Safety helmets", "خوذات السلامة", "42.00"),
    ("Electrical cabling 100m", "كابلات كهربائية 100 متر", "230.00"),
]


def line(index: int, qty: str, vat: str = "S") -> InvoiceLineIn:
    name_en, name_ar, price = ITEMS[index % len(ITEMS)]
    rate = "5" if vat == "S" else "0"
    return InvoiceLineIn(
        description=name_en,
        description_ar=name_ar,
        quantity=qty,
        unit_price=price,
        vat_category=vat,  # type: ignore[arg-type]
        vat_rate=rate,
        exemption_reason=(
            "Exempt supply — Article 46, Federal Decree-Law No. 8 of 2017" if vat == "E" else None
        ),
    )


def main() -> None:
    factory = get_sessionmaker()

    # Idempotency check via the users table (global identity, not under RLS).
    from app.models import User

    with factory() as db:
        if db.scalars(select(User).where(User.email == DEMO_EMAIL)).one_or_none():
            print("Demo tenant already seeded — nothing to do.")
            return

    with factory() as db:
        user, tenant, _ = auth_service.signup(
            db,
            SignupIn(
                email=DEMO_EMAIL,
                password="Demo12345!",
                full_name="Demo Owner",
                phone="+971501234567",
                company={
                    "legal_name_ar": "شركة الفوترة التجريبية ذ.م.م",
                    "legal_name_en": "Fawtara Demo Trading LLC",
                    "trn": DEMO_TRN,
                    "emirate": "Dubai",
                    "revenue_band": "lt_50m",
                },  # type: ignore[arg-type]
            ),
            ConsoleOTPProvider(),
        )
        tenant_id, user_id = tenant.id, user.id
        db.commit()

    with factory() as db:
        set_rls_context(db, tenant_id=tenant_id, user_id=user_id)
        repo = ContactRepository(db, tenant_id)
        for name_en, name_ar, trn, city in CONTACTS:
            repo.add(Contact(name_en=name_en, name_ar=name_ar, trn=trn, city=city, emirate=city))
        db.commit()

    today = date.today()

    def create(
        number: str,
        buyer_trn: str,
        buyer_name: str,
        days_ago: int,
        lines: list[InvoiceLineIn],
        *,
        validate: bool = False,
        send: bool = False,
        execute: bool = True,
    ) -> None:
        with factory() as db:
            set_rls_context(db, tenant_id=tenant_id, user_id=user_id)
            tenant = db.get(Tenant, tenant_id)
            assert tenant is not None
            payload = InvoiceCreateIn(
                invoice_number=number,
                issue_date=today - timedelta(days=days_ago),
                buyer=BuyerIn(name=buyer_name, trn=buyer_trn),
                lines=lines,
            )
            canonical = invoice_service.build_canonical(tenant, payload, None)
            invoice, _, _ = invoice_service.create_invoice(
                db,
                InvoiceRepository(db, tenant_id),
                tenant,
                canonical,
                contact_id=None,
                created_by=user_id,
            )
            transmission_id: uuid.UUID | None = None
            if validate:
                invoice_service.validate_invoice(db, invoice, actor_id=user_id)
            if send:
                transmission = transmission_service.queue_transmission(
                    db, invoice, actor_id=user_id
                )
                transmission_id = transmission.id
            db.commit()
        if transmission_id is not None and execute:
            transmission_service.execute_transmission(transmission_id, tenant_id)

    n = 0

    def number() -> str:
        nonlocal n
        n += 1
        return f"INV-2026-{n:04d}"

    # 12 ACCEPTED (archived)
    for i in range(12):
        create(
            number(),
            ACCEPT,
            "Gulf Builders LLC",
            days_ago=44 - 3 * i,
            lines=[line(i, str(1 + i % 4)), line(i + 1, "2")],
            validate=True,
            send=True,
        )
    # 4 REJECTED (two rejection codes)
    for i, trn in enumerate((REJECT_A, REJECT_A, REJECT_B, REJECT_B)):
        create(
            number(),
            trn,
            "Falcon Insurance Brokers",
            9 - i,
            [line(i, "3")],
            validate=True,
            send=True,
        )
    # 3 SENT (awaiting webhook)
    for i in range(3):
        create(
            number(),
            PROCESSING,
            "Oasis Manufacturing LLC",
            5 - i,
            [line(i, "1")],
            validate=True,
            send=True,
        )
    # 2 QUEUED (queued, worker hasn't picked them up)
    for i in range(2):
        create(
            number(),
            ACCEPT,
            "Doha Foods Trading",
            2,
            [line(i, "4")],
            validate=True,
            send=True,
            execute=False,
        )
    # 2 ERROR (permanent gateway failure)
    for i in range(2):
        create(
            number(),
            PERMANENT,
            "Precision Repairs LLC",
            12 - i,
            [line(i, "2")],
            validate=True,
            send=True,
        )
    # 2 VALIDATED (ready to send)
    for i in range(2):
        create(number(), ACCEPT, "Gulf Builders LLC", 1, [line(i, "5")], validate=True)
    # 5 DRAFT: 3 clean + 2 with an invalid buyer TRN (fixable in the UI)
    for i in range(3):
        create(number(), ACCEPT, "Marina Heights Properties", 7 + i, [line(i, "1")])
    for i in range(2):
        create(number(), "123", "Walk-in Customer", 6 + i, [line(i, "1")])

    with factory() as db:
        set_rls_context(db, tenant_id=tenant_id, user_id=user_id)
        invoices, total = InvoiceRepository(db, tenant_id).list_filtered(limit=200)
        statuses: dict[str, int] = {}
        for invoice in invoices:
            statuses[invoice.status] = statuses.get(invoice.status, 0) + 1
    print(f"Seeded {total} invoices for {DEMO_EMAIL}: {statuses}")


if __name__ == "__main__":
    main()
