"""Organization permission helpers."""

from collections.abc import Mapping
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db.models import Exists, OuterRef, Q
from rest_framework import permissions
from rest_framework.request import Request

from app.models import CustomUser
from league.models import League
from org.features import FeatureKey, org_has_feature
from org.models import Organization, OrgUser
from user.permissions import is_site_admin


def is_org_owner(user: CustomUser | AnonymousUser, obj: Any) -> bool:
    """Check if user is the org owner.

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute
    organization = getattr(obj, "organization", obj)

    return organization.owner_id == user.pk


def has_org_admin_access(user: CustomUser | AnonymousUser, obj: Any) -> bool:
    """Check if user is a site admin, org owner, or org admin.

    Site admin = ``is_staff || is_superuser`` (matches the frontend
    permission-hook convention so the gate is identical on both sides).

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute (e.g., ProfileClaimRequest)
    organization = getattr(obj, "organization", obj)

    return (
        user.is_staff
        or user.is_superuser
        or is_org_owner(user, organization)
        or organization.admins.filter(pk=user.pk).exists()
    )


def has_org_staff_access(user: CustomUser | AnonymousUser, obj: Any) -> bool:
    """Check if user has staff access to org (owner, admin, or staff).

    Args:
        user: The user to check
        obj: Either an Organization object, or any object with an .organization attribute
    """
    if not user.is_authenticated:
        return False

    # Handle objects that have an organization attribute
    organization = getattr(obj, "organization", obj)

    return (
        has_org_admin_access(user, obj)
        or organization.staff.filter(pk=user.pk).exists()
    )


def is_org_role_holder(
    user: CustomUser | AnonymousUser, organization: Organization | int
) -> bool:
    """Owner, admin, staff or promoter of the org. No site-admin shortcut."""
    if not user.is_authenticated:
        return False
    org_pk = organization if isinstance(organization, int) else organization.pk
    uid = user.pk
    return (
        Organization.objects.nocache()
        .filter(pk=org_pk)
        .filter(
            Q(owner_id=uid)
            | Exists(
                Organization.admins.through.objects.filter(
                    organization_id=OuterRef("pk"), customuser_id=uid
                )
            )
            | Exists(
                Organization.staff.through.objects.filter(
                    organization_id=OuterRef("pk"), customuser_id=uid
                )
            )
            | Exists(
                Organization.promoters.through.objects.filter(
                    organization_id=OuterRef("pk"), customuser_id=uid
                )
            )
        )
        .exists()
    )


def has_org_promoter_access(
    user: CustomUser | AnonymousUser, organization: Organization | int
) -> bool:
    return org_has_feature(organization, FeatureKey.PROMOTION) and (
        is_site_admin(user) or is_org_role_holder(user, organization)
    )


def can_view_org_members(
    user: CustomUser | AnonymousUser, organization: Organization | int
) -> bool:
    """Org staff and staff of any of the org's leagues always; plain members
    only while the member list isn't private. One uncached query."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    org_pk = organization if isinstance(organization, int) else organization.pk
    uid = user.pk
    league_staff = League.objects.filter(organization_id=OuterRef("pk")).filter(
        Q(admins__pk=uid) | Q(staff__pk=uid)
    )
    member = OrgUser.objects.filter(organization_id=OuterRef("pk"), user_id=uid)
    return (
        Organization.objects.nocache()
        .filter(pk=org_pk)
        .filter(
            Q(owner_id=uid)
            | Exists(
                Organization.admins.through.objects.filter(
                    organization_id=OuterRef("pk"), customuser_id=uid
                )
            )
            | Exists(
                Organization.staff.through.objects.filter(
                    organization_id=OuterRef("pk"), customuser_id=uid
                )
            )
            | Exists(league_staff)
            | (Q(members_private=False) & Exists(member))
        )
        .exists()
    )


def _payload_lists_user(user: CustomUser, data: Mapping[str, Any]) -> bool:
    owner = data.get("owner")
    if isinstance(owner, Mapping) and owner.get("pk") == user.pk:
        return True
    return any(
        entry.get("pk") == user.pk
        for key in ("admins", "staff")
        for entry in data.get(key) or ()
    )


def _payload_has_user(user: CustomUser, entries: Any) -> bool:
    return any(entry.get("pk") == user.pk for entry in entries or ())


def org_admin_staff_from_payload(
    user: CustomUser | AnonymousUser, data: Mapping[str, Any]
) -> tuple[bool, bool]:
    """(has_org_admin_access, has_org_staff_access) read from a serialized
    OrganizationSerializer payload instead of the database."""
    if not user.is_authenticated:
        return False, False
    owner = data.get("owner")
    is_admin = (
        is_site_admin(user)
        or (isinstance(owner, Mapping) and owner.get("pk") == user.pk)
        or _payload_has_user(user, data.get("admins"))
    )
    return is_admin, is_admin or _payload_has_user(user, data.get("staff"))


def can_view_org_members_from_payload(
    user: CustomUser | AnonymousUser, data: Mapping[str, Any]
) -> bool:
    """can_view_org_members for a serialized OrganizationSerializer payload,
    skipping the query when the payload already names the user as staff."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser or _payload_lists_user(user, data):
        return True
    return can_view_org_members(user, data["pk"])


class IsOrgOwner(permissions.BasePermission):
    """Permission check for organization owner access."""

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return is_org_owner(request.user, obj) or request.user.is_superuser


class IsOrgAdmin(permissions.BasePermission):
    """Permission check for organization admin access."""

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return has_org_admin_access(request.user, obj)


class IsOrgStaff(permissions.BasePermission):
    """Permission check for organization staff access (includes admins)."""

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        return has_org_staff_access(request.user, obj)
