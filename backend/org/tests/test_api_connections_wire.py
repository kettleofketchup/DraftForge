import json
import os
from pathlib import Path
from typing import Any

from org.api_connections.serializers import ConnectionSerializer
from org.api_connections.types import MmrPullConfig, MmrPushConfig
from org.models import OrgApiConnection, OrgApiMmrDelivery
from org.tests.test_api_tokens import ApiTokenBase

WIRE_FIXTURE = Path(__file__).parent / "golden" / "api_connection_wire.json"
STABLE: dict[str, object] = {
    "id": 1,
    "user_id": 2,
    "issued_by_id": 2,
    "created_by": 2,
    "updated_by": 2,
    "prefix": "fixture1",
    "token": "dfk_fixture_token",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
    "revoked_at": "2026-01-02T00:00:00Z",
    "delivery_id": "a3b0c442-98fc-4c1c-b39d-5c4f2f0e1a11",
    "due_at": "2026-01-01T00:00:00Z",
}


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                STABLE[key] if key in STABLE and child is not None else _stable(child)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_stable(child) for child in value]
    return value


class ConnectionWireFixtureTests(ApiTokenBase):
    """Pins real serializer output; the frontend Zod schemas parse the same file."""

    def setUp(self) -> None:
        super().setUp()
        self.client.force_authenticate(self.admin)
        self.url = f"/api/organizations/{self.org.pk}/api-connections/"

    def wire(self) -> dict[str, Any]:
        legacy = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "Legacy route"},
            format="json",
        )
        self.assertEqual(legacy.status_code, 201, legacy.data)
        backfilled = OrgApiConnection.objects.create(
            organization=self.org,
            name="Backfilled",
            created_by=self.admin,
            updated_by=self.admin,
            enabled=True,
            inbound_enabled=True,
            operations=["mmr:read", "mmr:write"],
            legacy_backfilled=True,
        )
        self.assertEqual(backfilled.mmr_push_config, {})
        self.assertEqual(backfilled.mmr_pull_config, {})
        listed = self.client.get(self.url)
        self.assertEqual(listed.status_code, 200)
        rows = sorted(listed.json(), key=lambda row: row["name"])
        legacy_row = next(row for row in rows if row["name"] == "Legacy route")
        rotated = self.client.post(
            f"{self.url}{legacy_row['id']}/rotate-key/", {}, format="json"
        )
        self.assertEqual(rotated.status_code, 201, rotated.data)
        for revision, reason in enumerate(("auth_failed", "origin_changed"), start=1):
            OrgApiMmrDelivery.objects.create(
                connection=backfilled,
                game_type=1,
                revision=revision,
                payload={"entries": [{"mmr": 4200, "steam_id": 76561198000000000}]},
                destination_origin="https://ratings.example",
                state=OrgApiMmrDelivery.State.PAUSED,
                attempts=3,
                last_reason=reason,
            )
        deliveries = self.client.get(f"{self.url}{backfilled.pk}/deliveries/")
        self.assertEqual(deliveries.status_code, 200, deliveries.data)
        return {
            "connections": _stable(rows),
            "delivery_page": _stable(deliveries.json()),
            "issue_key_response": _stable(rotated.json()),
        }

    def test_unsaved_config_serializes_with_defaults(self) -> None:
        row = OrgApiConnection.objects.create(organization=self.org, name="Stream")
        data = ConnectionSerializer(row).data
        self.assertEqual(data["mmr_push_config"], MmrPushConfig().model_dump())
        self.assertEqual(data["mmr_pull_config"], MmrPullConfig().model_dump())

    def test_wire_fixture_matches_serializer_output(self) -> None:
        wire = self.wire()
        text = json.dumps(wire, indent=2, sort_keys=True) + "\n"
        if os.environ.get("DF_UPDATE_WIRE_FIXTURE"):
            WIRE_FIXTURE.write_text(text, encoding="utf-8")
        self.assertEqual(json.loads(WIRE_FIXTURE.read_text(encoding="utf-8")), wire)
