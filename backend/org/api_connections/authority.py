from app.models import CustomUser
from org.api_connections.lifecycle import handle_credential_owner_loss
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.feature_keys import FeatureKey
from org.models import OrgApiConnection
from org.permissions import has_org_admin_access

DIRECTION_FEATURES: dict[str, FeatureKey] = {
    "mmr_push": FeatureKey.MMR_SYNC,
    "mmr_pull": FeatureKey.MMR_SYNC,
    "promotion_push": FeatureKey.PROMOTION,
}


def assert_connection_authority(
    connection: OrgApiConnection,
    *,
    direction: str,
    requester: CustomUser | None = None,
    testing: bool = False,
) -> None:
    current = OrgApiConnection.objects.select_related("organization").get(
        pk=connection.pk
    )
    if direction not in DIRECTION_FEATURES or current.archived_at is not None:
        raise not_permitted()
    org = current.organization
    if testing:
        if requester is None or not requester.is_active:
            raise not_permitted()
        require_org_admin(requester, org, None)
    elif not current.enabled or not getattr(current, f"{direction}_enabled"):
        raise not_permitted()
    principal_id = (
        current.outbound_authorizer_id
        if current.outbound_auth == "none"
        else current.outbound_credential_owner_id
    )
    principal = CustomUser.objects.filter(pk=principal_id).first()
    if (
        principal is None
        or not principal.is_active
        or not has_org_admin_access(principal, org)
    ):
        if principal is not None:
            handle_credential_owner_loss(principal, organization_id=org.pk)
        raise not_permitted()
    if current.outbound_auth != "none" and not current.outbound_credential_ciphertext:
        raise not_permitted()
    require_feature(org, DIRECTION_FEATURES[direction])
