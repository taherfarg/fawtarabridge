import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_token,
    decode_token,
    hash_password,
    sha256_hex,
    verify_password,
)
from app.db.session import set_rls_context
from app.models import OtpCode, RefreshToken, Tenant, TenantMembership, User
from app.models.enums import Role
from app.schemas.auth import SignupIn, TokenPairOut
from app.services.otp import OTPProvider


def _issue_token_pair(db: Session, user: User, tenant_id: uuid.UUID, role: Role) -> TokenPairOut:
    settings = get_settings()
    access = create_token(
        token_type="access",
        user_id=user.id,
        tenant_id=tenant_id,
        role=role.value,
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
    )
    refresh = create_token(
        token_type="refresh",
        user_id=user.id,
        tenant_id=tenant_id,
        role=role.value,
        ttl=timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(
        RefreshToken(
            user_id=user.id,
            tenant_id=tenant_id,
            token_hash=sha256_hex(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    return TokenPairOut(access_token=access, refresh_token=refresh)


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    diag = getattr(exc.orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) or str(exc)
    if "trn" in constraint:
        return AppError("tenant.trn_exists", status_code=409, field="company.trn")
    if "email" in constraint:
        return AppError("auth.email_exists", status_code=409, field="email")
    raise exc


def signup(
    db: Session, payload: SignupIn, otp_provider: OTPProvider
) -> tuple[User, Tenant, TokenPairOut]:
    email = payload.email.lower()
    if db.scalars(select(User).where(User.email == email)).one_or_none() is not None:
        raise AppError("auth.email_exists", status_code=409, field="email")

    # IDs are generated client-side so the RLS GUCs can be set BEFORE the inserts —
    # the new rows must satisfy their own policies (no bypass role exists).
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    set_rls_context(db, tenant_id=tenant_id, user_id=user_id)

    user = User(
        id=user_id,
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
    )
    tenant = Tenant(
        id=tenant_id,
        legal_name_ar=payload.company.legal_name_ar,
        legal_name_en=payload.company.legal_name_en,
        trn=payload.company.trn,
        license_no=payload.company.license_no,
        emirate=payload.company.emirate,
        address=payload.company.address,
        revenue_band=payload.company.revenue_band,
    )
    try:
        # Staged flushes: without relationship() mappings SQLAlchemy does not order
        # inserts across these tables, and the membership FK needs both parents.
        db.add_all([user, tenant])
        db.flush()
        db.add(TenantMembership(tenant_id=tenant_id, user_id=user_id, role=Role.OWNER))
        db.flush()
    except IntegrityError as exc:
        raise _translate_integrity_error(exc) from exc

    tokens = _issue_token_pair(db, user, tenant_id, Role.OWNER)
    _create_otp(db, user, otp_provider)
    return user, tenant, tokens


def login(
    db: Session, email: str, password: str
) -> tuple[User, TokenPairOut, uuid.UUID, list[TenantMembership]]:
    user = db.scalars(select(User).where(User.email == email.lower())).one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AppError("auth.invalid_credentials", status_code=401)
    if not user.is_active:
        raise AppError("auth.user_inactive", status_code=403)

    set_rls_context(db, user_id=user.id)
    memberships = list(
        db.scalars(
            select(TenantMembership)
            .where(TenantMembership.user_id == user.id)
            .order_by(TenantMembership.created_at)
        ).all()
    )
    if not memberships:
        raise AppError("auth.no_tenant", status_code=403)

    active = memberships[0]
    tokens = _issue_token_pair(db, user, active.tenant_id, active.role)
    return user, tokens, active.tenant_id, memberships


def refresh_tokens(db: Session, refresh_token: str) -> TokenPairOut:
    payload = decode_token(refresh_token, expected_type="refresh")
    user_id = uuid.UUID(payload["sub"])
    tenant_id = uuid.UUID(payload["tid"])
    set_rls_context(db, user_id=user_id)

    stored = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(refresh_token))
    ).one_or_none()
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        raise AppError("auth.token_invalid", status_code=401)

    membership = db.scalars(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id, TenantMembership.tenant_id == tenant_id
        )
    ).one_or_none()
    if membership is None:
        raise AppError("auth.not_member", status_code=403)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError("auth.user_inactive", status_code=403)

    stored.revoked_at = now  # rotation: a refresh token is single-use
    return _issue_token_pair(db, user, tenant_id, membership.role)


def logout(db: Session, refresh_token: str) -> None:
    payload = decode_token(refresh_token, expected_type="refresh")
    set_rls_context(db, user_id=uuid.UUID(payload["sub"]))
    stored = db.scalars(
        select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(refresh_token))
    ).one_or_none()
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = datetime.now(UTC)


def switch_tenant(db: Session, user_id: uuid.UUID, target_tenant_id: uuid.UUID) -> TokenPairOut:
    set_rls_context(db, user_id=user_id)
    membership = db.scalars(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == target_tenant_id,
        )
    ).one_or_none()
    if membership is None:
        raise AppError("auth.not_member", status_code=403)
    user = db.get(User, user_id)
    assert user is not None  # FK guarantees existence
    return _issue_token_pair(db, user, target_tenant_id, membership.role)


def _create_otp(db: Session, user: User, provider: OTPProvider) -> None:
    settings = get_settings()
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        OtpCode(
            user_id=user.id,
            code_hash=sha256_hex(code),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes),
        )
    )
    provider.send(user.phone, code)


def request_otp(db: Session, user_id: uuid.UUID, provider: OTPProvider) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise AppError("auth.not_authenticated", status_code=401)
    _create_otp(db, user, provider)


def verify_otp(db: Session, user_id: uuid.UUID, code: str) -> None:
    settings = get_settings()
    otp = db.scalars(
        select(OtpCode)
        .where(
            OtpCode.user_id == user_id,
            OtpCode.purpose == "phone_verification",
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    ).one_or_none()
    now = datetime.now(UTC)
    if otp is None:
        raise AppError("otp.not_found", status_code=400)
    if otp.expires_at < now:
        raise AppError("otp.expired", status_code=400)
    if otp.attempts >= settings.otp_max_attempts:
        raise AppError("otp.too_many_attempts", status_code=429)
    if otp.code_hash != sha256_hex(code):
        otp.attempts += 1
        # Persist the failed attempt even though we raise: the request-scoped
        # transaction would otherwise roll it back and unlimited guessing wins.
        db.commit()
        raise AppError("otp.invalid", status_code=400)

    otp.consumed_at = now
    user = db.get(User, user_id)
    assert user is not None
    user.phone_verified = True
