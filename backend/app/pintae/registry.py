from app.config import get_settings
from app.pintae.base import InvoiceEngine


class UnknownSpecVersionError(LookupError):
    def __init__(self, spec_version: str) -> None:
        super().__init__(f"no engine registered for spec version '{spec_version}'")
        self.spec_version = spec_version


_engines: dict[str, InvoiceEngine] = {}


def register_engine(engine: InvoiceEngine) -> None:
    if engine.spec_version in _engines:
        raise ValueError(f"engine for '{engine.spec_version}' already registered")
    _engines[engine.spec_version] = engine


def get_engine(spec_version: str | None = None) -> InvoiceEngine:
    version = spec_version or get_settings().pintae_default_spec_version
    try:
        return _engines[version]
    except KeyError:
        raise UnknownSpecVersionError(version) from None


def available_spec_versions() -> list[str]:
    return sorted(_engines)
