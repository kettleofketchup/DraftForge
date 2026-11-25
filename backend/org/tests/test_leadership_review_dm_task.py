import json
from typing import Any
from unittest.mock import MagicMock, patch

import requests
from celery.exceptions import Retry
from django.test import SimpleTestCase, override_settings

from discordbot.dm import V2_FLAG, DMOutcome
from discordbot.dm_ledger import ClaimResult
from discordbot.models import DMKind, DMStatus, DMSubject
from discordbot.schemas import PlannedMessage
from org.leadership.tasks import send_leadership_review_dms

PAYLOAD: dict[str, Any] = {
    "flags": V2_FLAG,
    "components": [{"type": 10, "content": "**Rate your captain: Ava (Cup)**"}],
}


def _planned(**overrides: Any) -> PlannedMessage:
    base: dict[str, Any] = dict(
        snapshot_id=7,
        part=1,
        parts=2,
        trait_ids=[3, 4],
        rater_org_user_id=11,
        recipient_user_id=21,
        organization_id=5,
        discord_user_id="123456",
        skip=None,
        payload=PAYLOAD,
    )
    base.update(overrides)
    return PlannedMessage(**base)


def _outcome(status: DMStatus) -> DMOutcome:
    return DMOutcome(
        status=status, ledger_id=1, message_id=None, channel_id=None, error_code=None
    )


@patch("org.leadership.tasks.send_dm", return_value=_outcome(DMStatus.SENT))
@patch("org.leadership.tasks.plan_review_dms")
class SendLeadershipReviewDMsTaskTest(SimpleTestCase):
    def test_task_sends_one_dm_per_planned_message(
        self, plan: MagicMock, send: MagicMock
    ) -> None:
        plan.return_value = [
            _planned(),
            _planned(part=2, trait_ids=[5]),
            _planned(rater_org_user_id=12, recipient_user_id=22, discord_user_id=None),
        ]
        result = send_leadership_review_dms.run(9, [7])
        plan.assert_called_once_with(9, [7])
        self.assertEqual(send.call_count, 3)
        first = send.call_args_list[0].args[0]
        self.assertEqual(first.kind, DMKind.LEADERSHIP_REVIEW)
        self.assertEqual(
            first.idempotency_key, "leadership_review:snapshot:7:rater:11:part:1"
        )
        self.assertEqual(first.subject, (DMSubject.CAPTAIN_SNAPSHOT, 7))
        self.assertEqual(
            dict(first.context),
            {"snapshot_id": 7, "part": 1, "parts": 2, "trait_ids": [3, 4]},
        )
        self.assertEqual(first.flags, V2_FLAG)
        self.assertEqual(first.components, PAYLOAD["components"])
        self.assertEqual(first.discord_user_id, "123456")
        self.assertEqual(first.recipient_user_id, 21)
        self.assertEqual(first.organization_id, 5)
        self.assertIsNone(first.skip_status)
        self.assertEqual(
            send.call_args_list[1].args[0].idempotency_key,
            "leadership_review:snapshot:7:rater:11:part:2",
        )
        self.assertIsNone(send.call_args_list[2].args[0].discord_user_id)
        self.assertEqual(result, {"planned": 3, "sent": 3})

    def test_disabled_plan_claims_skipped_disabled(
        self, plan: MagicMock, send: MagicMock
    ) -> None:
        plan.return_value = [_planned(skip="disabled")]
        send.return_value = _outcome(DMStatus.SKIPPED_DISABLED)
        result = send_leadership_review_dms.run(9, [7])
        self.assertEqual(send.call_args.args[0].skip_status, DMStatus.SKIPPED_DISABLED)
        self.assertEqual(result, {"planned": 1, "skipped_disabled": 1})

    def test_rejected_bot_token_stops_sending(
        self, plan: MagicMock, send: MagicMock
    ) -> None:
        plan.return_value = [_planned(), _planned(part=2, trait_ids=[5])]
        send.return_value = DMOutcome(
            status=DMStatus.FAILED,
            ledger_id=1,
            message_id=None,
            channel_id=None,
            error_code=None,
            auth_rejected=True,
        )
        result = send_leadership_review_dms.run(9, [7])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result, {"planned": 2, "failed": 1, "auth_rejected": 1})

    def test_task_plan_unreachable_raises_for_retry(
        self, plan: MagicMock, send: MagicMock
    ) -> None:
        plan.return_value = None
        with (
            patch.object(
                send_leadership_review_dms, "retry", side_effect=Retry()
            ) as retry,
            self.assertRaises(Retry),
        ):
            send_leadership_review_dms.run(9, [7])
        retry.assert_called_once()
        send.assert_not_called()

    def test_task_options(self, plan: MagicMock, send: MagicMock) -> None:
        self.assertTrue(send_leadership_review_dms.acks_late)
        self.assertEqual(
            send_leadership_review_dms.name,
            "org.leadership.tasks.send_leadership_review_dms",
        )


def _discord_response(body: dict[str, Any]) -> requests.Response:
    resp = requests.Response()
    resp.status_code = 200
    resp._content = json.dumps(body).encode()
    resp.headers["Content-Type"] = "application/json"
    return resp


@override_settings(TEST=False)
@patch("discordbot.dm.finalize_dm", return_value=True)
@patch("discordbot.dm.mark_dm_sending", return_value=True)
@patch("discordbot.dm.claim_dm")
@patch("discordbot.utils._acquire_rate_limit_token", return_value=True)
@patch("discordbot.utils.requests.request")
@patch("org.leadership.tasks.plan_review_dms")
class ReviewDMPacingTest(SimpleTestCase):
    def test_task_paces_through_token_bucket(
        self,
        plan: MagicMock,
        request: MagicMock,
        bucket: MagicMock,
        claim: MagicMock,
        mark: MagicMock,
        finalize: MagicMock,
    ) -> None:
        plan.return_value = [
            _planned(rater_org_user_id=r, part=p) for r in (11, 12) for p in (1, 2)
        ]
        claim.side_effect = [
            ClaimResult(
                id=i, granted=True, status=DMStatus.PENDING, attempts=1, created=True
            )
            for i in range(1, 5)
        ]
        calls: list[str] = []

        def fake(method: str, url: str, **kwargs: object) -> requests.Response:
            calls.append(url)
            return _discord_response({"id": "900"})

        request.side_effect = fake
        bucket.side_effect = lambda *a, **k: calls.append("token") or True
        result = send_leadership_review_dms.run(9, [7])
        self.assertEqual(result, {"planned": 4, "sent": 4})
        posts = [i for i, c in enumerate(calls) if c.endswith("/messages")]
        self.assertEqual(len(posts), 4)
        for i in posts:
            self.assertEqual(calls[i - 1], "token")
        self.assertGreaterEqual(bucket.call_count, 8)
