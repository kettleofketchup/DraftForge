from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import NotAuthenticated, PermissionDenied

from app.models import CustomUser, Organization
from app.permissions_org import (
    has_org_admin_access,
    has_org_staff_access,
    is_org_role_holder,
    is_site_admin,
)
from org.features import FeatureKey, org_has_feature

FEATURE_LOCKED = "feature_locked"
NOT_PERMITTED = "not_permitted"


def feature_locked() -> PermissionDenied:
    return PermissionDenied(
        detail={
            "code": FEATURE_LOCKED,
            "detail": "This feature is not enabled for this organization.",
        }
    )


def not_permitted() -> PermissionDenied:
    return PermissionDenied(
        detail={
            "code": NOT_PERMITTED,
            "detail": "You do not have permission to perform this action.",
        }
    )


def require_feature(org: Organization | int, feature: FeatureKey | str) -> None:
    if not org_has_feature(org, FeatureKey(feature)):
        raise feature_locked()


def _require_authenticated(user: CustomUser | AnonymousUser) -> None:
    if not user.is_authenticated:
        raise NotAuthenticated()


def require_promoter(user: CustomUser | AnonymousUser, org: Organization) -> None:
    require_feature(org, FeatureKey.PROMOTION)
    _require_authenticated(user)
    if not (is_site_admin(user) or is_org_role_holder(user, org)):
        raise not_permitted()


def require_org_staff(
    user: CustomUser | AnonymousUser,
    org: Organization,
    feature: FeatureKey | None,
) -> None:
    if feature is not None:
        require_feature(org, feature)
    _require_authenticated(user)
    if not has_org_staff_access(user, org):
        raise not_permitted()


def require_org_admin(
    user: CustomUser | AnonymousUser,
    org: Organization,
    feature: FeatureKey | None,
) -> None:
    if feature is not None:
        require_feature(org, feature)
    _require_authenticated(user)
    if not has_org_admin_access(user, org):
        raise not_permitted()
