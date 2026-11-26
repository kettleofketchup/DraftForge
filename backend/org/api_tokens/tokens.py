import hashlib
import hmac
import secrets
from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from app.models import CustomUser
from org.api_tokens.operations import default_operations, parse_operations
from org.models import Organization, OrgApiToken, OrgLog
from telemetry.logging import get_logger

log = get_logger(__name__)

TOKEN_SCHEME = "dfk"
PREFIX_BYTES = 6
SECRET_BYTES = 32


@dataclass(frozen=True)
class IssuedToken:
    token: OrgApiToken
    raw: str


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_prefix() -> str:
    while True:
        prefix = secrets.token_hex(PREFIX_BYTES)
        if not OrgApiToken.objects.filter(prefix=prefix).exists():
            return prefix


def issue_token(
    org: Organization,
    user: CustomUser,
    name: str,
    *,
    operations: Iterable[str] | None = None,
) -> IssuedToken:
    """Create a token. Without ``operations`` it gets the MMR pair only.

    Raises ValueError for an empty or unknown operation list. Callers check
    that the org has each operation's feature before issuing.
    """
    granted = (
        default_operations()
        if operations is None
        else parse_operations([str(op) for op in operations])
    )
    prefix = _new_prefix()
    secret = secrets.token_urlsafe(SECRET_BYTES)
    with transaction.atomic():
        token = OrgApiToken.objects.create(
            organization=org,
            user=user,
            name=name,
            prefix=prefix,
            secret_hash=hash_secret(secret),
            operations=granted,
        )
        OrgLog.objects.create(
            organization=org,
            actor=user,
            action="create_api_token",
            details={
                "token_id": token.pk,
                "prefix": prefix,
                "name": name,
                "operations": granted,
            },
        )
    log.info(
        "org_api_token_created",
        system="org",
        subsystem="api_tokens",
        org_id=org.pk,
        token_id=token.pk,
        user_id=user.pk,
        operations=granted,
    )
    return IssuedToken(token=token, raw=f"{TOKEN_SCHEME}_{prefix}_{secret}")


def parse_raw(raw: str) -> tuple[str, str] | None:
    parts = raw.split("_", 2)
    if len(parts) != 3 or parts[0] != TOKEN_SCHEME or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def lookup_token(raw: str) -> OrgApiToken | None:
    parsed = parse_raw(raw)
    if parsed is None:
        return None
    prefix, secret = parsed
    token = (
        OrgApiToken.objects.select_related("user", "organization")
        .filter(prefix=prefix)
        .first()
    )
    if token is None:
        return None
    if not hmac.compare_digest(token.secret_hash, hash_secret(secret)):
        return None
    return token


def revoke_token(token: OrgApiToken, actor: CustomUser) -> OrgApiToken:
    if token.revoked_at is not None:
        return token
    with transaction.atomic():
        token.revoked_at = timezone.now()
        token.revoked_by = actor
        token.save(update_fields=["revoked_at", "revoked_by"])
        OrgLog.objects.create(
            organization_id=token.organization_id,
            actor=actor,
            action="revoke_api_token",
            target_user_id=token.user_id,
            details={"token_id": token.pk, "prefix": token.prefix},
        )
    log.info(
        "org_api_token_revoked",
        system="org",
        subsystem="api_tokens",
        org_id=token.organization_id,
        token_id=token.pk,
        actor_id=actor.pk,
    )
    return token
