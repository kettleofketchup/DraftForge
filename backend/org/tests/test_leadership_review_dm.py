import math
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz
from rest_framework.test import APIClient
from structlog.testing import capture_logs

from discordbot import dm_ledger
from discordbot.dm_keys import leadership_review_key
from discordbot.dm_ledger import DMClaim, DMFinal
from discordbot.internal_leadership_views import LeadershipReviewClickThrottle
from discordbot.models import DiscordDM, DMKind, DMStatus, DMSubject
from discordbot.payload_schema import DiscordMessage
from discordbot.schemas import ClickResult, PlannedMessage, ReviewDMPlanResponse
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership import lifecycle, review_dm
from org.leadership.constants import VoidKind
from org.leadership.kinds import LeadershipKind
from org.leadership.maintenance import reassign_member
from org.leadership.review_dm_render import (
    MAX_TRAITS_PER_MESSAGE,
    TraitRow,
    count_components,
    render_part,
)
from org.leadership.reviews import void_review, withdraw_review
from org.leadership.traits import materialize_traits
from org.models import Organization
from org.models_leadership import (
    CaptainReview,
    CaptainReviewDraft,
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.tests.leadership_base import LeadershipTestCase

SITE = "https://df.example"


def _walk(components: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for comp in components:
        yield comp
        yield from _walk(comp.get("components", []))


def _texts(payload: dict[str, Any]) -> list[str]:
    return [c["content"] for c in _walk(payload["components"]) if c["type"] == 10]


def _custom_ids(payload: dict[str, Any]) -> list[str]:
    return [c["custom_id"] for c in _walk(payload["components"]) if "custom_id" in c]


def _rows(n: int) -> list[TraitRow]:
    return [
        TraitRow(trait_id=100 + i, label=f"Trait {i}", active=True) for i in range(n)
    ]


class ReviewDMPreviewTest(LeadershipTestCase):
    def test_preview_with_sending_off_uses_defaults_without_writing_or_sending(
        self,
    ) -> None:
        self.assertFalse(CaptainTrait.objects.filter(organization=self.org).exists())
        self.assertFalse(
            OrgLeadershipSettings.objects.filter(organization=self.org).exists()
        )
        client = self.client_for(self.admin)
        with (
            CaptureQueriesContext(connection) as queries,
            patch("requests.sessions.Session.request") as transport,
            patch("org.leadership.tasks.send_leadership_review_dms.delay") as enqueue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = client.get(self.url("review-dm-preview/"))
        self.assertEqual(response.status_code, 200)
        (message,) = response.json()["messages"]
        self.assertEqual(message["flags"], 32768)
        self.assertIn("**Communication**", _texts(message))
        self.assertIn("Sample Captain (Sample Event)", _texts(message)[0])
        self.assertIn("0 of 4 scored", _texts(message))
        self.assertFalse(
            any(
                q["sql"]
                .lstrip()
                .upper()
                .startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
                for q in queries
            )
        )
        transport.assert_not_called()
        enqueue.assert_not_called()

    def test_multipart_matches_production_renderer_with_configured_traits_and_window(
        self,
    ) -> None:
        for i, order in enumerate((7, 4, 2, 2, 9, 5, 1), start=1):
            CaptainTrait.objects.create(
                pk=100 + i,
                organization=self.org,
                key=f"trait{i}",
                label=f"Skill {i}",
                order=order,
                active=i != 5,
            )
        OrgLeadershipSettings.objects.create(
            organization=self.org, review_window_hours=24
        )
        now = tz.now()
        with patch("org.leadership.views.timezone.now", return_value=now):
            response = self.client_for(self.admin).get(self.url("review-dm-preview/"))
        self.assertEqual(response.status_code, 200)
        rows = [
            TraitRow(trait_id=index, label=f"Skill {i}", active=True)
            for index, i in enumerate((7, 3, 4, 2, 6, 1), start=1)
        ]
        expected = [
            DiscordMessage.model_validate(
                render_part(
                    captain_name="Sample Captain",
                    event_name="Sample Event",
                    close_at=now + timedelta(hours=24),
                    part=index,
                    parts=2,
                    traits=part,
                    scores={},
                    snapshot_id=1,
                    site_url="https://example.invalid/events/1?review=1",
                    state="progress",
                )
            ).model_dump(mode="json")
            for index, part in enumerate((rows[:5], rows[5:]), start=1)
        ]
        self.assertEqual(response.json(), {"messages": expected})
        CaptainTrait.objects.filter(organization=self.org).update(active=False)
        empty = self.client_for(self.admin).get(self.url("review-dm-preview/"))
        self.assertEqual(empty.json(), {"messages": []})

    def test_preview_uses_the_settings_permission_and_organization_boundary(
        self,
    ) -> None:
        url = self.url("review-dm-preview/")
        self.org.staff.add(self.cap_a)
        for user in (self.cap_a, self.mates_a[0]):
            with self.subTest(user=user.pk):
                self.assertEqual(self.client_for(user).get(url).status_code, 403)
        self.assertIn(APIClient().get(url).status_code, (401, 403))
        other = Organization.objects.create(name="Other club", owner=self.cap_b)
        set_org_feature(other, FeatureKey.LEADERSHIP, enabled=True, actor=None)
        self.assertEqual(self.client_for(self.cap_b).get(url).status_code, 403)
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        self.assertEqual(self.client_for(self.admin).get(url).status_code, 403)


@override_settings(SITE_URL=SITE)
class ReviewDMPlanTest(LeadershipTestCase):
    def enable(self, on: bool = True) -> None:
        OrgLeadershipSettings.objects.update_or_create(
            organization=self.org, defaults={"review_dms_enabled": on}
        )

    def set_traits(self, n: int) -> list[CaptainTrait]:
        CaptainTrait.objects.filter(organization=self.org).delete()
        return [
            CaptainTrait.objects.create(
                organization=self.org, key=f"t{i}", label=f"Trait {i}", order=n - i
            )
            for i in range(n)
        ]

    def snap_ids(self) -> list[int]:
        return list(
            EventCaptain.objects.filter(event=self.event)
            .order_by("pk")
            .values_list("pk", flat=True)
        )

    def plan(self) -> list[PlannedMessage]:
        return review_dm.plan(self.event.pk, self.snap_ids(), now=tz.now())

    def test_plan_chunks_traits_into_parts(self) -> None:
        self.enable()
        self.run_snapshot()
        snap = self.snapshot(self.cap_a)
        for n in range(1, 9):
            with self.subTest(n=n):
                traits = self.set_traits(n)
                expected = [t.pk for t in sorted(traits, key=lambda t: (t.order, t.pk))]
                msgs = [m for m in self.plan() if m.snapshot_id == snap.pk]
                parts = math.ceil(n / MAX_TRAITS_PER_MESSAGE)
                self.assertEqual(len(msgs), parts * len(self.mates_a))
                rater = msgs[0].rater_org_user_id
                mine = [m for m in msgs if m.rater_org_user_id == rater]
                self.assertEqual([m.part for m in mine], list(range(1, parts + 1)))
                self.assertTrue(all(m.parts == parts for m in mine))
                self.assertEqual([i for m in mine for i in m.trait_ids], expected)
                self.assertTrue(
                    all(len(m.trait_ids) <= MAX_TRAITS_PER_MESSAGE for m in mine)
                )

    def test_original_job_cannot_send_after_reclose(self) -> None:
        self.enable()
        self.run_snapshot()
        original_ids = self.snap_ids()
        lifecycle.void_event(self.event, now=tz.now())
        late = self.make_user("late_review_dm")
        self.admit(late)
        self.team_a.members.add(late)
        self.run_snapshot()
        self.assertIn(self.ou(late), self.snapshot(self.cap_a).teammates.all())
        self.assertEqual(review_dm.plan(self.event.pk, original_ids, now=tz.now()), [])

    def test_plan_rejects_disabled_leadership(self) -> None:
        self.enable()
        self.run_snapshot()
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        self.assertEqual(self.plan(), [])

    def test_payload_component_budget(self) -> None:
        self.enable()
        self.run_snapshot()
        for n in range(1, 9):
            with self.subTest(n=n):
                self.set_traits(n)
                for msg in self.plan():
                    self.assertLessEqual(count_components(msg.payload), 40)
                    self.assertEqual(msg.payload["flags"], 1 << 15)
        five = render_part(
            captain_name="Ava",
            event_name="Cup",
            close_at=tz.now(),
            part=1,
            parts=1,
            traits=_rows(5),
            scores={},
            snapshot_id=1,
            site_url=SITE,
            state="progress",
        )
        self.assertEqual(count_components(five), 39)

    def test_plan_only_teammates_not_captain(self) -> None:
        self.enable()
        self.run_snapshot()
        snap = self.snapshot(self.cap_a)
        snap.teammates.add(self.ou(self.cap_a))
        msgs = [m for m in self.plan() if m.snapshot_id == snap.pk]
        self.assertEqual(
            {m.rater_org_user_id for m in msgs}, {self.ou(u).pk for u in self.mates_a}
        )
        self.assertEqual(
            {m.recipient_user_id for m in msgs}, {u.pk for u in self.mates_a}
        )
        self.assertTrue(all(m.organization_id == self.org.pk for m in msgs))

    def test_plan_no_discord_id_entry(self) -> None:
        self.enable()
        self.mates_a[0].discordId = "123456789012345678"
        self.mates_a[0].save(update_fields=["discordId"])
        self.run_snapshot()
        by_user = {m.recipient_user_id: m for m in self.plan()}
        self.assertEqual(
            by_user[self.mates_a[0].pk].discord_user_id, "123456789012345678"
        )
        self.assertIsNone(by_user[self.mates_a[1].pk].discord_user_id)
        self.assertIsNone(by_user[self.mates_a[1].pk].skip)

    def test_plan_disabled_marks_skip(self) -> None:
        self.run_snapshot()
        msgs = self.plan()
        self.assertTrue(msgs)
        self.assertTrue(all(m.skip == "disabled" for m in msgs))
        self.enable()
        self.assertTrue(all(m.skip is None for m in self.plan()))

    def test_plan_skips_voided_and_closed(self) -> None:
        self.enable()
        self.run_snapshot()
        a, b = self.snapshot(self.cap_a), self.snapshot(self.cap_b)
        EventCaptain.objects.filter(pk=a.pk).update(voided_at=tz.now())
        self.assertEqual({m.snapshot_id for m in self.plan()}, {b.pk})
        EventCaptain.objects.filter(pk=b.pk).update(
            window_closes_at=tz.now() - timedelta(minutes=1)
        )
        self.assertEqual(self.plan(), [])

    def test_plan_ignores_other_event_snapshots(self) -> None:
        self.enable()
        self.run_snapshot()
        self.assertEqual(
            review_dm.plan(self.event.pk + 999, self.snap_ids(), now=tz.now()), []
        )

    def test_plan_materializes_default_traits(self) -> None:
        self.enable()
        self.run_snapshot()
        self.assertFalse(CaptainTrait.objects.filter(organization=self.org).exists())
        msgs = self.plan()
        pks = set(
            CaptainTrait.objects.filter(organization=self.org).values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(len(pks), 4)
        for msg in msgs:
            self.assertTrue(set(msg.trait_ids) <= pks)
            self.assertEqual(len(msg.trait_ids), 4)

    def test_custom_ids_under_100_chars(self) -> None:
        self.enable()
        self.run_snapshot()
        snap = self.snapshot(self.cap_a)
        self.set_traits(8)
        msgs = [m for m in self.plan() if m.snapshot_id == snap.pk]
        for msg in msgs:
            ids = _custom_ids(msg.payload)
            self.assertEqual(len(ids), len(msg.trait_ids) * 5)
            self.assertEqual(len(set(ids)), len(ids))
            for cid in ids:
                self.assertLessEqual(len(cid), 100)
                self.assertTrue(cid.startswith(f"lr:{snap.pk}:"))
            self.assertEqual(
                {cid.rsplit(":", 1)[1] for cid in ids}, {"1", "2", "3", "4", "5"}
            )

    def test_initial_state_status_line(self) -> None:
        self.enable()
        self.run_snapshot()
        self.set_traits(4)
        one = self.plan()[0]
        texts = _texts(one.payload)
        self.assertIn("0 of 4 scored", texts)
        self.assertNotIn("Part", texts[0])
        self.assertIn("Rate your captain", texts[0])
        self.set_traits(7)
        msgs = [m for m in self.plan() if m.rater_org_user_id == one.rater_org_user_id]
        first, second = (_texts(m.payload) for m in msgs)
        saves = "Your review saves once both messages are complete."
        self.assertIn(f"0 of 5 scored in this message\n{saves}", first)
        self.assertIn(f"0 of 2 scored in this message\n{saves}", second)
        self.assertIn("Part 1 of 2", first[0])
        self.assertIn("Part 2 of 2", second[0])

    def test_site_link_button(self) -> None:
        self.enable()
        self.run_snapshot()
        msg = self.plan()[0]
        links = [c for c in _walk(msg.payload["components"]) if c.get("style") == 5]
        self.assertEqual(len(links), 1)
        self.assertEqual(
            links[0]["url"],
            f"{SITE}/events/{self.event.pk}?review={msg.snapshot_id}",
        )


class RenderPartTest(LeadershipTestCase):
    def render(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = dict(
            captain_name="Ava",
            event_name="Thursday Inhouse",
            close_at=tz.now(),
            part=1,
            parts=1,
            traits=_rows(3),
            scores={},
            snapshot_id=9,
            site_url=f"{SITE}/events/1?review=9",
            state="progress",
        )
        base.update(overrides)
        return render_part(**base)

    def test_chosen_button_is_primary(self) -> None:
        payload = self.render(scores={100: 4})
        buttons = {
            c["custom_id"]: c["style"]
            for c in _walk(payload["components"])
            if "custom_id" in c
        }
        self.assertEqual(buttons["lr:9:100:4"], 1)
        self.assertEqual(buttons["lr:9:100:3"], 2)
        self.assertEqual(buttons["lr:9:101:4"], 2)
        self.assertIn("1 of 3 scored", _texts(payload))

    def test_states(self) -> None:
        close = tz.now()
        ts = int(close.timestamp())
        cases = {
            "saved": f"Review saved. You can change it until <t:{ts}:f>.",
            "traits_changed": "Traits changed. Finish on the site.",
            "closed": "Reviews for this event are closed for now.",
        }
        for state, line in cases.items():
            with self.subTest(state=state):
                self.assertIn(line, _texts(self.render(state=state, close_at=close)))

    def test_inactive_trait_label_and_buttons_enabled(self) -> None:
        traits = [TraitRow(trait_id=1, label="Old", active=False), *_rows(1)]
        payload = self.render(traits=traits)
        self.assertIn("**Old** (no longer used)", _texts(payload))
        self.assertFalse(any(c.get("disabled") for c in _walk(payload["components"])))

    def test_header_escapes_markdown(self) -> None:
        payload = self.render(captain_name="*Ava*", event_name="Cup_1")
        self.assertIn("\\*Ava\\*", _texts(payload)[0])
        self.assertIn("Cup\\_1", _texts(payload)[0])

    def test_rejects_too_many_traits(self) -> None:
        with self.assertRaises(ValueError):
            self.render(traits=_rows(6))


@override_settings(INTERNAL_SERVICE_TOKEN="test-token", SITE_URL=SITE)
class ReviewDMPlanEndpointTest(LeadershipTestCase):
    path = "/api/internal/leadership/review-dms/plan/"

    def test_plan_endpoint_requires_internal_auth(self) -> None:
        client = APIClient()
        resp = client.post(
            self.path, {"event_id": 1, "snapshot_ids": []}, format="json"
        )
        self.assertIn(resp.status_code, (401, 403))
        client.credentials(HTTP_X_INTERNAL_TOKEN="wrong")
        resp = client.post(
            self.path, {"event_id": 1, "snapshot_ids": []}, format="json"
        )
        self.assertIn(resp.status_code, (401, 403))

    def test_plan_endpoint_shape(self) -> None:
        OrgLeadershipSettings.objects.create(
            organization=self.org, review_dms_enabled=True
        )
        self.run_snapshot()
        ids = list(EventCaptain.objects.values_list("pk", flat=True))
        client = APIClient()
        client.credentials(HTTP_X_INTERNAL_TOKEN="test-token")
        resp = client.post(
            self.path, {"event_id": self.event.pk, "snapshot_ids": ids}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        body = ReviewDMPlanResponse.model_validate(resp.json())
        self.assertEqual(len(body.messages), len(self.mates_a) + len(self.mates_b))
        self.assertEqual(set(resp.json()), {"messages"})

    def test_plan_endpoint_rejects_bad_body(self) -> None:
        client = APIClient()
        client.credentials(HTTP_X_INTERNAL_TOKEN="test-token")
        resp = client.post(self.path, {"event_id": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)


CHANNEL = "555000000000000001"


@override_settings(SITE_URL=SITE)
class ReviewClickTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        people = [*self.mates_a, *self.mates_b, self.cap_a, self.cap_b]
        for i, user in enumerate(people):
            user.discordId = str(710000000000000000 + i)
            user.save(update_fields=["discordId"])
        self.run_snapshot()
        self.snap = self.snapshot(self.cap_a)
        self.traits = self.active_traits()
        self.rater = self.mates_a[0]
        self._next_message = 900000000000000000
        self.msg, self.row_id = self.send(self.rater)

    def test_click_rejects_disabled_leadership(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        for trait in self.traits:
            self.assertIsNotNone(self.click(trait, 4).ephemeral)
        self.assertFalse(CaptainReview.objects.exists())
        self.assertFalse(CaptainReviewDraft.objects.exists())

    def test_click_still_works_when_review_sends_disabled(self) -> None:
        OrgLeadershipSettings.objects.update_or_create(
            organization=self.org, defaults={"review_dms_enabled": False}
        )
        for trait in self.traits:
            self.assertIsNone(self.click(trait, 4).ephemeral)
        self.assertEqual(CaptainReview.objects.count(), 1)

    def active_traits(self) -> list[CaptainTrait]:
        return sorted(
            (t for t in materialize_traits(self.org.pk) if t.active),
            key=lambda t: (t.order, t.pk),
        )

    def message_id(self) -> str:
        self._next_message += 1
        return str(self._next_message)

    def send(
        self,
        user: Any,
        *,
        trait_ids: list[int] | None = None,
        part: int = 1,
        parts: int = 1,
        finalize: bool = True,
    ) -> tuple[str, int]:
        ids = trait_ids or [t.pk for t in self.traits]
        now = tz.now()
        claim = dm_ledger.claim(
            DMClaim(
                kind=DMKind.LEADERSHIP_REVIEW,
                idempotency_key=leadership_review_key(
                    snapshot_id=self.snap.pk,
                    rater_org_user_id=self.ou(user).pk,
                    part=part,
                ),
                claim_token="tok",
                discord_user_id=user.discordId,
                subject_type=DMSubject.CAPTAIN_SNAPSHOT,
                subject_id=self.snap.pk,
                context={
                    "snapshot_id": self.snap.pk,
                    "part": part,
                    "parts": parts,
                    "trait_ids": ids,
                },
                has_components=True,
            ),
            now=now,
        )
        message = self.message_id()
        if finalize:
            dm_ledger.finalize(
                claim.id,
                DMFinal(
                    status=DMStatus.SENT,
                    discord_channel_id=CHANNEL,
                    discord_message_id=message,
                ),
                claim_token="tok",
                now=now,
            )
        return message, claim.id

    def click(
        self,
        trait: CaptainTrait,
        score: int,
        *,
        user: Any = None,
        message: str | None = None,
    ) -> ClickResult:
        return review_dm.apply_click(
            discord_user_id=(user or self.rater).discordId,
            discord_message_id=message or self.msg,
            discord_channel_id=CHANNEL,
            snapshot_id=self.snap.pk,
            trait_id=trait.pk,
            score=score,
            now=tz.now(),
        )

    def status(self, result: ClickResult) -> str:
        assert result.message is not None
        return _texts(result.message)[-1]

    def chosen(self, result: ClickResult) -> set[str]:
        assert result.message is not None
        return {
            c["custom_id"]
            for c in _walk(result.message["components"])
            if c.get("style") == 1 and "custom_id" in c
        }

    def draft(self, user: Any = None) -> CaptainReviewDraft | None:
        return CaptainReviewDraft.objects.filter(
            event_captain=self.snap, rater=self.ou(user or self.rater)
        ).first()

    def scores_of(self, user: Any) -> set[tuple[int, int]]:
        return set(
            CaptainTraitScore.objects.filter(
                review__event_captain=self.snap,
                review__rater=self.ou(user),
            ).values_list("trait_id", "score")
        )

    def row(self, row_id: int | None = None) -> DiscordDM:
        return DiscordDM.objects.get(pk=row_id or self.row_id)

    def test_partial_click_stores_draft_only(self) -> None:
        rating = self.points(self.cap_a, LeadershipKind.CAPTAIN_RATING.value)
        result = self.click(self.traits[0], 4)
        self.assertIsNone(result.ephemeral)
        self.assertEqual(self.status(result), "1 of 4 scored")
        self.assertEqual(
            self.chosen(result), {f"lr:{self.snap.pk}:{self.traits[0].pk}:4"}
        )
        draft = self.draft()
        assert draft is not None
        self.assertEqual(draft.scores, {str(self.traits[0].pk): 4})
        self.assertFalse(CaptainReview.objects.exists())
        self.assertEqual(
            self.points(self.cap_a, LeadershipKind.CAPTAIN_RATING.value), rating
        )
        self.assertIsNone(self.snapshot(self.cap_a).released_at)

    def test_completing_click_submits_review_equal_to_site(self) -> None:
        values = [5, 4, 3, 2]
        results = [self.click(t, v) for t, v in zip(self.traits, values, strict=True)]
        for result in results[:-1]:
            self.assertIsNone(result.ephemeral)
            self.assertIn("scored", self.status(result))
        close = int(self.snapshot(self.cap_a).window_closes_at.timestamp())
        self.assertEqual(
            self.status(results[-1]),
            f"Review saved. You can change it until <t:{close}:f>.",
        )
        self.review(
            self.mates_a[1],
            self.cap_a,
            {t.key: v for t, v in zip(self.traits, values, strict=True)},
        )
        self.assertEqual(
            {(t, s) for t, s in self.scores_of(self.rater)},
            self.scores_of(self.mates_a[1]),
        )
        self.assertEqual(
            CaptainReview.objects.filter(voided_at__isnull=True).count(), 2
        )

    def test_seed_from_live_review(self) -> None:
        self.review(self.rater, self.cap_a, 3)
        result = self.click(self.traits[0], 5)
        self.assertIn("Review saved.", self.status(result))
        self.assertEqual(
            self.scores_of(self.rater),
            {(self.traits[0].pk, 5)} | {(t.pk, 3) for t in self.traits[1:]},
        )
        self.assertEqual(len(self.chosen(result)), 4)

    def test_reseed_after_site_edit(self) -> None:
        self.click(self.traits[0], 1)
        self.review(self.rater, self.cap_a, 2)
        self.click(self.traits[1], 5)
        self.assertEqual(
            self.scores_of(self.rater),
            {(self.traits[1].pk, 5)}
            | {(t.pk, 2) for t in self.traits if t != self.traits[1]},
        )
        self.review(self.rater, self.cap_a, 3)
        self.click(self.traits[2], 1)
        self.assertEqual(
            self.scores_of(self.rater),
            {(self.traits[2].pk, 1)}
            | {(t.pk, 3) for t in self.traits if t != self.traits[2]},
        )

    def test_never_seed_from_withdrawn(self) -> None:
        self.review(self.rater, self.cap_a, 3)
        withdraw_review(
            self.org,
            event_id=self.event.pk,
            captain_org_user_id=self.snap.captain_id,
            rater=self.ou(self.rater),
            now=tz.now(),
        )
        result = self.click(self.traits[0], 4)
        self.assertEqual(self.status(result), "1 of 4 scored")
        draft = self.draft()
        assert draft is not None
        self.assertEqual(draft.scores, {str(self.traits[0].pk): 4})
        self.assertEqual(CaptainReview.objects.get().void_kind, VoidKind.WITHDRAWN)

    def test_refusal_codes_ephemeral(self) -> None:
        def voided() -> None:
            lifecycle.void_event(self.event, now=tz.now())

        def closed() -> None:
            self.expire_window()

        def not_in_pool() -> None:
            self.snap.teammates.remove(self.ou(self.rater))

        def moderated() -> None:
            review = self.review(self.rater, self.cap_a, 3)
            void_review(
                self.org,
                review_id=review.pk,
                actor=self.admin,
                reason="abuse",
                now=tz.now(),
            )

        cases = [
            (voided, "Reviews for this event are closed.", True),
            (closed, "The review window has closed.", True),
            (not_in_pool, "You cannot review this captain.", False),
            (moderated, "This review was removed by an organizer.", False),
        ]
        for setup, text, rerender in cases:
            with self.subTest(case=setup.__name__), transaction.atomic():
                setup()
                result = self.click(self.traits[0], 4)
                self.assertEqual(result.ephemeral, text)
                if rerender:
                    self.assertEqual(
                        self.status(result),
                        "Reviews for this event are closed for now.",
                    )
                else:
                    self.assertIsNone(result.message)
                draft = self.draft()
                self.assertTrue(draft is None or draft.scores == {})
                transaction.set_rollback(True)

    def test_closed_rerender_keeps_buttons_enabled(self) -> None:
        lifecycle.void_event(self.event, now=tz.now())
        result = self.click(self.traits[0], 4)
        assert result.message is not None
        buttons = [c for c in _walk(result.message["components"]) if c["type"] == 2]
        self.assertEqual(len(buttons), len(self.traits) * 5 + 1)
        self.assertFalse(any(b.get("disabled") for b in buttons))

    def test_void_then_reclose_same_message_works(self) -> None:
        lifecycle.void_event(self.event, now=tz.now())
        self.assertIsNotNone(self.click(self.traits[0], 4).ephemeral)
        self.run_snapshot()
        self.assertEqual(self.snapshot(self.cap_a).pk, self.snap.pk)
        result = self.click(self.traits[0], 4)
        self.assertIsNone(result.ephemeral)
        self.assertEqual(self.status(result), "1 of 4 scored")

    def test_lost_finalize_first_click_repairs_row(self) -> None:
        mate = self.mates_a[1]
        message, row_id = self.send(mate, finalize=False)
        self.assertEqual(self.row(row_id).status, DMStatus.PENDING)
        result = self.click(self.traits[0], 3, user=mate, message=message)
        self.assertIsNone(result.ephemeral)
        row = self.row(row_id)
        self.assertEqual(row.status, DMStatus.SENT)
        self.assertEqual(row.discord_message_id, message)
        self.assertEqual(row.discord_channel_id, CHANNEL)
        self.assertEqual(row.click_count, 1)
        draft = self.draft(mate)
        assert draft is not None
        self.assertEqual(draft.scores, {str(self.traits[0].pk): 3})
        other = self.click(self.traits[1], 3, user=mate, message=self.message_id())
        self.assertEqual(other.ephemeral, review_dm.OUT_OF_DATE)

    def test_skipped_row_never_attached(self) -> None:
        mate = self.mates_a[1]
        now = tz.now()
        dm_ledger.claim(
            DMClaim(
                kind=DMKind.LEADERSHIP_REVIEW,
                idempotency_key=leadership_review_key(
                    snapshot_id=self.snap.pk,
                    rater_org_user_id=self.ou(mate).pk,
                    part=1,
                ),
                claim_token="tok",
                discord_user_id=mate.discordId,
                subject_type=DMSubject.CAPTAIN_SNAPSHOT,
                subject_id=self.snap.pk,
                context={
                    "snapshot_id": self.snap.pk,
                    "part": 1,
                    "parts": 1,
                    "trait_ids": [t.pk for t in self.traits],
                },
                has_components=True,
                initial_status=DMStatus.SKIPPED_TEST_MODE,
            ),
            now=now,
        )
        result = self.click(self.traits[0], 3, user=mate, message=self.message_id())
        self.assertEqual(result.ephemeral, review_dm.OUT_OF_DATE)
        self.assertIsNone(self.draft(mate))

    def test_merge_kept_account_no_spurious_traits_changed(self) -> None:
        keep_user = self.make_user("ld_keep")
        keep = self.admit(keep_user)
        discord_id = self.rater.discordId
        reassign_member(self.ou(self.rater), keep, now=tz.now())
        self.rater.discordId = ""
        self.rater.save(update_fields=["discordId"])
        keep_user.discordId = discord_id
        keep_user.save(update_fields=["discordId"])
        results = [self.click(t, 4, user=keep_user) for t in self.traits]
        for result in results[:-1]:
            self.assertIsNone(result.ephemeral)
            self.assertNotIn("Traits changed", self.status(result))
        self.assertIn("Review saved.", self.status(results[-1]))
        self.assertEqual(
            CaptainReview.objects.get(voided_at__isnull=True).rater_id, keep.pk
        )

    def test_two_part_completion_states(self) -> None:
        CaptainTrait.objects.filter(organization=self.org).delete()
        traits = [
            CaptainTrait.objects.create(
                organization=self.org, key=f"t{i}", label=f"Trait {i}", order=i
            )
            for i in range(7)
        ]
        self.traits = traits
        mate = self.mates_a[1]
        first, _ = self.send(
            mate, trait_ids=[t.pk for t in traits[:5]], part=1, parts=2
        )
        second, _ = self.send(
            mate, trait_ids=[t.pk for t in traits[5:]], part=2, parts=2
        )
        saves = "Your review saves once both messages are complete."
        result = self.click(traits[5], 2, user=mate, message=second)
        self.assertEqual(self.status(result), f"1 of 2 scored in this message\n{saves}")
        result = self.click(traits[6], 2, user=mate, message=second)
        self.assertEqual(self.status(result), f"2 of 2 scored in this message\n{saves}")
        for trait in traits[:4]:
            result = self.click(trait, 3, user=mate, message=first)
        self.assertEqual(self.status(result), f"4 of 5 scored in this message\n{saves}")
        self.assertFalse(CaptainReview.objects.exists())
        result = self.click(traits[4], 3, user=mate, message=first)
        self.assertIn("Review saved.", self.status(result))
        self.assertEqual(
            self.scores_of(mate),
            {(t.pk, 3) for t in traits[:5]} | {(t.pk, 2) for t in traits[5:]},
        )
        result = self.click(traits[5], 4, user=mate, message=second)
        self.assertIn("Review saved.", self.status(result))
        self.assertIn((traits[5].pk, 4), self.scores_of(mate))

    def test_wrong_clicker_not_yours(self) -> None:
        result = self.click(self.traits[0], 4, user=self.mates_a[1])
        self.assertEqual(result.ephemeral, review_dm.NOT_YOURS)
        self.assertIsNone(result.message)
        self.assertIsNone(self.draft(self.mates_a[1]))
        self.assertEqual(self.row().click_count, 0)

    def test_forwarded_message_no_row_out_of_date(self) -> None:
        result = self.click(
            self.traits[0], 4, user=self.mates_a[1], message=self.message_id()
        )
        self.assertEqual(result.ephemeral, review_dm.OUT_OF_DATE)
        self.assertIsNone(result.message)

    def test_out_of_date_message_id(self) -> None:
        result = self.click(self.traits[0], 4, message=self.message_id())
        self.assertEqual(result.ephemeral, review_dm.OUT_OF_DATE)
        self.assertIsNone(result.message)
        self.assertIsNone(self.draft())

    def test_deactivated_trait_refused_and_label_suffix(self) -> None:
        dropped = self.traits[1]
        CaptainTrait.objects.filter(pk=dropped.pk).update(active=False)
        refused = self.click(dropped, 4)
        self.assertEqual(refused.ephemeral, review_dm.TRAIT_UNUSED)
        self.assertIsNone(refused.message)
        result = self.click(self.traits[0], 4)
        self.assertEqual(self.status(result), "1 of 3 scored")
        texts = _texts(result.message or {})
        self.assertIn(f"**{dropped.label}** (no longer used)", texts)
        for trait in (self.traits[2], self.traits[3]):
            result = self.click(trait, 4)
        self.assertIn("Review saved.", self.status(result))

    def test_new_trait_traits_changed(self) -> None:
        CaptainTrait.objects.create(
            organization=self.org, key="new", label="New", order=99
        )
        result = self.click(self.traits[0], 4)
        self.assertEqual(self.status(result), "Traits changed. Finish on the site.")
        for trait in self.traits[1:]:
            result = self.click(trait, 4)
        self.assertEqual(self.status(result), "Traits changed. Finish on the site.")
        self.assertFalse(CaptainReview.objects.exists())

    def test_click_recorded_once(self) -> None:
        self.click(self.traits[0], 4)
        row = self.row()
        self.assertEqual(row.click_count, 1)
        self.assertIsNotNone(row.first_clicked_at)
        self.assertEqual(row.first_clicked_at, row.last_clicked_at)

    def test_click_log_has_no_message_id_with_user_id(self) -> None:
        mate = self.mates_a[1]
        message, _ = self.send(mate, finalize=False)
        with capture_logs() as logs:
            self.click(self.traits[0], 4)
            self.click(self.traits[0], 4, user=mate, message=message)
            self.click(self.traits[0], 4, message=self.message_id())
            for trait in self.traits:
                self.click(trait, 5)
        self.assertTrue(logs)
        for entry in logs:
            self.assertFalse(
                "discord_message_id" in entry and "discord_user_id" in entry, entry
            )
        clicks = [e for e in logs if e["event"] == "leadership_review_click"]
        self.assertTrue(clicks)
        for entry in clicks:
            self.assertEqual(entry["system"], "org")
            self.assertEqual(entry["subsystem"], "leadership")


@override_settings(INTERNAL_SERVICE_TOKEN="test-token", SITE_URL=SITE)
class ReviewClickEndpointTest(LeadershipTestCase):
    path = "/api/internal/discord/leadership/review-click/"

    def setUp(self) -> None:
        super().setUp()
        self.discord_id = "720000000000000001"
        cache.delete(f"throttle_leadership_review_click_{self.discord_id}")

    def body(self, **overrides: Any) -> dict[str, Any]:
        return {
            "discord_user_id": self.discord_id,
            "discord_message_id": "730000000000000001",
            "discord_channel_id": CHANNEL,
            "interaction_id": "740000000000000001",
            "snapshot_id": 1,
            "trait_id": 1,
            "score": 3,
            **overrides,
        }

    def internal(self) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_X_INTERNAL_TOKEN="test-token")
        return client

    def test_endpoint_requires_internal_auth(self) -> None:
        resp = APIClient().post(self.path, self.body(), format="json")
        self.assertIn(resp.status_code, (401, 403))

    def test_endpoint_shape(self) -> None:
        resp = self.internal().post(self.path, self.body(), format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            resp.json(), {"message": None, "ephemeral": review_dm.OUT_OF_DATE}
        )

    def test_endpoint_rejects_bad_body(self) -> None:
        for bad in ({"score": 6}, {"snapshot_id": 0}, {"discord_user_id": "x"}):
            with self.subTest(bad=bad):
                resp = self.internal().post(self.path, self.body(**bad), format="json")
                self.assertEqual(resp.status_code, 400)

    def test_endpoint_throttled(self) -> None:
        client = self.internal()
        with patch.object(LeadershipReviewClickThrottle, "rate", "2/min"):
            for _ in range(2):
                resp = client.post(self.path, self.body(), format="json")
                self.assertEqual(resp.status_code, 200, resp.content)
            resp = client.post(self.path, self.body(), format="json")
            self.assertEqual(resp.status_code, 429)
            other = client.post(
                self.path,
                self.body(discord_user_id="720000000000000002"),
                format="json",
            )
            self.assertEqual(other.status_code, 200)
        cache.delete("throttle_leadership_review_click_720000000000000002")
