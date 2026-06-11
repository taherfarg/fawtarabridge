from app.models import Transmission
from app.repositories.base import TenantScopedRepository


class TransmissionRepository(TenantScopedRepository[Transmission]):
    model = Transmission

    def list_for_invoice(self, invoice_id) -> list[Transmission]:  # type: ignore[no-untyped-def]
        stmt = (
            self.query()
            .where(Transmission.invoice_id == invoice_id)
            .order_by(Transmission.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_needing_attention(self) -> list[Transmission]:
        """Dead-lettered or permanently failed — the admin-visibility view (FR-4.2)."""
        stmt = (
            self.query()
            .where(Transmission.status.in_(("dead_letter", "failed")))
            .order_by(Transmission.updated_at.desc())
        )
        return list(self.session.scalars(stmt).all())
