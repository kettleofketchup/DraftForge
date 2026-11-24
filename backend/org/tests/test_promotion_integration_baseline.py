"""Behaviour the SFG event-promotion sync builds on.

Each recorded send is its own DM even when it earns nothing, contribution
totals read only the contribution track, and a ``dfk_`` app token issued
through the API works on the merged MMR sync endpoint for its own org only.
"""

from django.utils import timezone

from events.tests.base import EventTestCase
from org.models import ContributionEntry, OrgUser, PromoSend
from org.standing import ledger
from org.standing.periods import parse_period
from org.tests.test_api_tokens import ApiTokenBase
from org.tests.test_promotion_sends import _SendFixture


class RepeatSendBaselineTest(_SendFixture):
    def test_repeat_non_earning_send_is_a_distinct_dm(self) -> None:
        first = self._send(self.promoter)
        repeat = self._send(self.promoter, text="Second nudge")
        other = self._send(self.promoter_b, text="Hello from another promoter")

        sends = list(
            PromoSend.objects.nocache()
            .filter(event=self.event, recipient=self.recipient)
            .order_by("pk")
        )
        self.assertEqual([s.pk for s in sends], [first.pk, repeat.pk, other.pk])
        self.assertEqual(len({s.pk for s in sends}), 3)
        self.assertEqual([s.earns_points for s in sends], [True, False, False])
        self.assertEqual(
            ContributionEntry.objects.nocache().filter(promo_send__in=sends).count(),
            1,
        )


class ContributionTotalBaselineTest(EventTestCase):
    def setUp(self) -> None:
        self.now = timezone.now()
        self.member = self.make_user()
        self.member_ou = OrgUser.objects.get(user=self.member, organization=self.org)

    def test_track_rows_excludes_leadership(self) -> None:
        ledger.award(
            org=self.org,
            user=self.member,
            kind="manual",
            points=3,
            occurred_at=self.now,
            reason="thanks",
        )
        ledger.award(
            org=self.org,
            user=self.member,
            kind="captained",
            points=5,
            occurred_at=self.now,
            event=self.event,
        )
        ContributionEntry.objects.create(
            org_user=self.member_ou,
            organization=self.org,
            track="conduct",
            kind="conduct_row",
            points=11,
            occurred_at=self.now,
        )
        all_time = parse_period(self.org, None)

        self.assertEqual(
            ledger.total(self.org.pk, track="contribution", period=all_time), 3
        )
        rows = list(
            ledger.sum_by_member(self.org.pk, track="contribution", period=all_time)
        )
        self.assertEqual(
            [(r["org_user"], r["total"]) for r in rows], [(self.member_ou.pk, 3)]
        )
        self.assertEqual(
            sorted(
                ledger.track_rows("contribution")
                .filter(org_user=self.member_ou)
                .values_list("kind", flat=True)
            ),
            ["manual"],
        )


class MergedAppTokenBaselineTest(ApiTokenBase):
    def test_merged_app_token_round_trip(self) -> None:
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            f"/api/organizations/{self.org.pk}/api-tokens/",
            {"name": "sfg-adapter"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        raw = created.data["token"]
        self.assertTrue(raw.startswith("dfk_"))

        client = self.bearer(raw)
        resp = client.get(self.sync_url())
        self.assertEqual(resp.status_code, 200)
        steam_ids = {m["steam_id"] for m in resp.data["members"]}
        self.assertIn(1001, steam_ids)
        self.assertNotIn(1003, steam_ids)

        self.assertEqual(client.get(self.sync_url(self.other_org)).status_code, 404)
