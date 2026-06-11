from app.asp.base import ASPAdapter
from app.asp.mock import MockASPAdapter
from app.config import get_settings

_ADAPTERS: dict[str, ASPAdapter] = {
    MockASPAdapter.name: MockASPAdapter(),
}


def get_asp_adapter(name: str | None = None) -> ASPAdapter:
    provider = name or get_settings().asp_provider
    try:
        return _ADAPTERS[provider]
    except KeyError:
        raise LookupError(f"unknown ASP provider '{provider}'") from None
