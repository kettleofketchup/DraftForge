from __future__ import annotations

import json
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from org.api_connections.crypto import canonical_origin, seal_credential
from org.api_connections.schemas import (
    ConnectionConfigError,
    validate_connection_config,
)
from org.api_connections.types import ConnectionConfig
from org.models import OrgApiConnection

if TYPE_CHECKING:
    from app.models import CustomUser


CONFIG_FIELDS = tuple(ConnectionConfig.model_fields)
WRITE_ONLY_FIELDS = {"outbound_credential", "clear_outbound_credential"}


def apply_config_patch(
    connection: OrgApiConnection,
    *,
    actor: CustomUser,
    patch: dict[str, object],
    expected_version: int,
) -> OrgApiConnection:
    if type(expected_version) is not int or expected_version < 1:
        raise ConnectionConfigError("invalid_config")
    if type(patch) is not dict or set(patch) - set(CONFIG_FIELDS) - WRITE_ONLY_FIELDS:
        raise ConnectionConfigError("invalid_config")
    replacement = patch.get("outbound_credential")
    clear = patch.get("clear_outbound_credential", False)
    if type(clear) is not bool or (
        "outbound_credential" in patch
        and (
            type(replacement) is not str
            or not replacement
            or "clear_outbound_credential" in patch
        )
    ):
        raise ConnectionConfigError("invalid_config")
    with transaction.atomic():
        current = OrgApiConnection.objects.select_for_update().get(
            pk=connection.pk, organization_id=connection.organization_id
        )
        if current.config_version != expected_version:
            raise ConnectionConfigError("configuration_changed")
        if current.archived_at is not None:
            raise ConnectionConfigError("connection_archived")
        raw = {field: getattr(current, field) for field in CONFIG_FIELDS}
        raw.update(
            {field: value for field, value in patch.items() if field in CONFIG_FIELDS}
        )
        config = validate_connection_config(raw)
        updates = config.model_dump(mode="json")
        updates.update(
            updated_by=actor,
            updated_at=timezone.now(),
            config_version=expected_version + 1,
        )
        old_origin = (
            canonical_origin(current.outbound_base_url)
            if current.outbound_base_url
            else None
        )
        new_origin = (
            canonical_origin(config.outbound_base_url)
            if config.outbound_base_url
            else None
        )
        if (
            current.outbound_credential_ciphertext
            and old_origin != new_origin
            and replacement is None
            and not clear
        ):
            raise ConnectionConfigError("credential_required_for_new_origin")
        if replacement is not None and (
            config.outbound_auth == "none" or new_origin is None
        ):
            raise ConnectionConfigError("invalid_config")
        if clear or config.outbound_auth == "none":
            updates.update(
                outbound_credential_ciphertext="",
                outbound_credential_key_id="",
                outbound_credential_owner=None,
                outbound_credential_set_at=None,
            )
        elif replacement is not None:
            envelope = seal_credential(
                replacement,
                org_id=current.organization_id,
                connection_id=current.pk,
                origin=new_origin,
            )
            updates.update(
                outbound_credential_ciphertext=envelope,
                outbound_credential_key_id=json.loads(envelope)["kid"],
                outbound_credential_owner=actor,
                outbound_credential_set_at=timezone.now(),
            )
        if config.outbound_auth != "none":
            if any(
                (
                    config.mmr_push_enabled,
                    config.mmr_pull_enabled,
                    config.promotion_push_enabled,
                )
            ) and not (
                replacement or (current.outbound_credential_ciphertext and not clear)
            ):
                raise ConnectionConfigError("credential_required")
            updates["outbound_authorizer"] = None
        elif any(
            (
                config.mmr_push_enabled,
                config.mmr_pull_enabled,
                config.promotion_push_enabled,
            )
        ) and (
            "outbound_auth" in patch
            or any(
                patch.get(field) is True
                for field in (
                    "mmr_push_enabled",
                    "mmr_pull_enabled",
                    "promotion_push_enabled",
                )
            )
        ):
            updates["outbound_authorizer"] = actor
        if not OrgApiConnection.objects.filter(
            pk=current.pk, config_version=expected_version
        ).update(**updates):
            raise ConnectionConfigError("configuration_changed")
        current.refresh_from_db()
        return current
