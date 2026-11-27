"""HTTP-interactions mode handler: discordbot.views.handle_message_component."""

import json

from django.test import TestCase
from django.utils import timezone

from discordbot import dm_ledger
from discordbot.dm_ledger import DMClaim, DMFinal
from discordbot.models import DiscordDM, DMKind, DMStatus
from discordbot.views import handle_message_component


def _payload(custom_id: str, *, guild_id: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "data": {"custom_id": custom_id},
        "message": {"id": "9001", "channel_id": "8001"},
    }
    if guild_id is None:
        payload["user"] = {"id": "1001", "username": "u"}
    else:
        payload["guild_id"] = guild_id
        payload["member"] = {"user": {"id": "1001", "username": "u"}}
    return payload


class HTTPModeDMClickTests(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        claim = dm_ledger.claim(
            DMClaim(
                kind=DMKind.SIGNUP_REMINDER,
                idempotency_key="k-views",
                claim_token="tok",
                discord_user_id="1001",
                has_components=True,
            ),
            now=now,
        )
        dm_ledger.finalize(
            claim.id,
            DMFinal(
                status=DMStatus.SENT,
                discord_channel_id="8001",
                discord_message_id="9001",
            ),
            claim_token="tok",
            now=now,
        )
        self.row_id = claim.id

    def _clicks(self) -> int:
        return DiscordDM.objects.get(pk=self.row_id).click_count

    def test_http_mode_dm_click_records(self) -> None:
        response = handle_message_component(_payload("event_signup:5", guild_id=None))
        self.assertEqual(json.loads(response.content), {"type": 6})
        self.assertEqual(self._clicks(), 1)

    def test_http_mode_guild_click_no_record(self) -> None:
        handle_message_component(_payload("event_signup:5", guild_id="77"))
        self.assertEqual(self._clicks(), 0)
