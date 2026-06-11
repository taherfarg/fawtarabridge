from app.models import ImportMappingTemplate
from app.repositories.base import TenantScopedRepository


class MappingTemplateRepository(TenantScopedRepository[ImportMappingTemplate]):
    model = ImportMappingTemplate

    def get_by_name(self, name: str) -> ImportMappingTemplate | None:
        return self.session.scalars(
            self.query().where(ImportMappingTemplate.name == name)
        ).one_or_none()

    def list_all(self) -> list[ImportMappingTemplate]:
        return list(self.session.scalars(self.query().order_by(ImportMappingTemplate.name)).all())
