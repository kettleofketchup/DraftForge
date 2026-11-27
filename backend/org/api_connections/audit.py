from app.models import CustomUser
from org.models import OrgApiConnection, OrgLog


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
