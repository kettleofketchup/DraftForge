from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, NotFound
from rest_framework.request import Request

from app.models import CustomUser
from org.api_tokens.throttle import check_and_record
from org.api_tokens.tokens import lookup_token
from org.feature_errors import not_permitted, require_feature
from org.features import FeatureKey
from org.models import Organization, OrgApiToken
from org.permissions import has_org_admin_access
from telemetry.logging import get_logger

log = get_logger(__name__)

KEYWORD = b"bearer"


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
        if not token.user.is_active:
            raise AuthenticationFailed("Token owner is inactive.")
        return token.user, token

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'


def gate_token_request(request: Request, org_id: int) -> Organization:
    token = request.auth
    if not isinstance(token, OrgApiToken):
        raise AuthenticationFailed("An org API token is required.")
    if token.organization_id != org_id:
        raise NotFound()
    org = token.organization
    require_feature(org, FeatureKey.MMR_SYNC)
    if not has_org_admin_access(token.user, org):
        raise not_permitted()
    check_and_record(token)
    return org
