from django.db import transaction

from app.models import CustomUser
from org.models import OrgApiConnection, OrgLog
from telemetry.logging import get_logger

log = get_logger(__name__)


def audit_connection(
    connection: OrgApiConnection,
    *,
    actor: CustomUser | None,
    action: str,
    fields: list[str] | None = None,
    credential_changed: bool = False,
) -> None:
    OrgLog.objects.create(
        organization_id=connection.organization_id,
        actor=actor,
        action=action,
        details={
            "connection_id": connection.pk,
            "fields": sorted(fields or []),
            "credential_changed": credential_changed,
        },
    )

    transaction.on_commit(
        lambda: log.info(
            "api_connection_lifecycle",
            system="org",
            subsystem="api_connections",
            connection_id=connection.pk,
            reason=action,
        )
    )
