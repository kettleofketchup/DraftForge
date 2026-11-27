from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.request import Request

from app.models import CustomUser
from org.api_tokens.operations import Operation, entitlement_for
from org.api_tokens.throttle import check_and_record
from org.api_tokens.tokens import lookup_token
from org.feature_errors import not_permitted, require_feature
from org.models import Organization, OrgApiToken
from org.permissions import has_org_admin_access
from telemetry.logging import get_logger

log = get_logger(__name__)

KEYWORD = b"bearer"
OPERATION_NOT_GRANTED = "operation_not_granted"


class OrgApiTokenAuthentication(BaseAuthentication):
    def authenticate(self, request: Request) -> tuple[CustomUser, OrgApiToken] | None:
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != KEYWORD:
            return None
        if len(parts) != 2:
            raise AuthenticationFailed("Invalid Authorization header.")
        token = lookup_token(parts[1].decode(errors="replace"))
        if token is None or not token.is_active:
            log.warning(
                "org_api_token_rejected",
                system="org",
                subsystem="api_tokens",
                reason="unknown" if token is None else "revoked",
                token_id=token.pk if token else None,
            )
            raise AuthenticationFailed("Invalid or revoked token.")
        if token.connection_id is not None:
            connection = token.connection
            if (
                connection.archived_at
                or not connection.enabled
                or not connection.inbound_enabled
            ):
                raise AuthenticationFailed("Connection is disabled.")
        if not token.user.is_active:
            raise AuthenticationFailed("Token owner is inactive.")
        return token.user, token

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'


def operation_not_granted() -> PermissionDenied:
    return PermissionDenied(
        detail={
            "code": OPERATION_NOT_GRANTED,
            "detail": "This token is not granted this operation.",
        }
    )


def gate_token_request(
    request: Request,
    org_id: int,
    *,
    operation: Operation | tuple[Operation, ...] = Operation.MMR_READ,
) -> Organization:
    """Authorize one app-token request for ``operation`` on ``org_id``.

    Runs on every request, retries included: the token's org, its grant, the
    operation's feature, the owner's current admin role, then the budget.
    Only a request that passes everything else is counted against the budget.
    """
    token = request.auth
    if not isinstance(token, OrgApiToken):
        raise AuthenticationFailed("An org API token is required.")
    if token.organization_id != org_id:
        raise NotFound()
    alternatives = operation if isinstance(operation, tuple) else (operation,)
    granted = next(
        (
            candidate
            for candidate in alternatives
            if token.grants(candidate)
            and (
                token.connection_id is None
                or str(candidate) in token.connection.operations
            )
        ),
        None,
    )
    if granted is None:
        log.info(
            "org_api_operation_denied",
            system="org",
            subsystem="api_tokens",
            org_id=org_id,
            token_id=token.pk,
            operation=str(operation),
        )
        raise operation_not_granted()
    org = token.organization
    require_feature(org, entitlement_for(granted))
    if not has_org_admin_access(token.user, org):
        raise not_permitted()
    check_and_record(token)
    return org
