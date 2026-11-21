"""Team draft REST permissions."""

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request

from app.permissions_tournament import can_edit_tournament


class CanEditDraft(permissions.BasePermission):
    """Permission check for draft editing via tournament access."""

    message = "You do not have permission to edit this draft."

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        # Draft belongs to a tournament
        if obj.tournament:
            return can_edit_tournament(request.user, obj.tournament)
        return False


class CanEditDraftRound(permissions.BasePermission):
    """Permission check for draft round editing via tournament access."""

    message = "You do not have permission to edit this draft round."

    def has_permission(self, request: Request, view: object) -> bool:
        """Allow authenticated users to proceed to object-level check."""
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request: Request, view: object, obj: Any) -> bool:
        # DraftRound belongs to Draft which belongs to Tournament
        if obj.draft and obj.draft.tournament:
            return can_edit_tournament(request.user, obj.draft.tournament)
        return False
