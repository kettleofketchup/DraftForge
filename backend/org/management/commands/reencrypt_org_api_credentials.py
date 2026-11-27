import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from org.api_connections.crypto import (
    CredentialError,
    canonical_origin,
    open_credential,
    seal_credential,
)
from org.models import OrgApiConnection


class Command(BaseCommand):
    help = (
        "Verify and re-encrypt outbound org credentials with the first configured key."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        count = 0
        ids = (
            OrgApiConnection.objects.exclude(outbound_credential_ciphertext="")
            .order_by("pk")
            .values_list("pk", flat=True)
            .iterator(chunk_size=100)
        )
        for connection_id in ids:
            try:
                with transaction.atomic():
                    connection = OrgApiConnection.objects.select_for_update().get(
                        pk=connection_id
                    )
                    if not connection.outbound_credential_ciphertext:
                        continue
                    binding = {
                        "org_id": connection.organization_id,
                        "connection_id": connection.pk,
                        "origin": canonical_origin(connection.outbound_base_url),
                    }
                    secret = open_credential(
                        connection.outbound_credential_ciphertext, **binding
                    )
                    if not options["dry_run"]:
                        envelope = seal_credential(secret, **binding)
                        if open_credential(envelope, **binding) != secret:
                            raise CredentialError("credential_verification_failed")
                        connection.outbound_credential_ciphertext = envelope
                        connection.outbound_credential_key_id = json.loads(envelope)[
                            "kid"
                        ]
                        connection.save(
                            update_fields=[
                                "outbound_credential_ciphertext",
                                "outbound_credential_key_id",
                            ]
                        )
                count += 1
                self.stdout.write(str(connection_id))
            except CredentialError as exc:
                raise CommandError(f"{connection_id}: {exc.code}") from None
        self.stdout.write(str(count))
