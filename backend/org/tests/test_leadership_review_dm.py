import math
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from django.test import override_settings
from django.utils import timezone as tz
from rest_framework.test import APIClient

from discordbot.schemas import PlannedMessage, ReviewDMPlanResponse
from org.leadership import review_dm
from org.leadership.review_dm_render import (
    MAX_TRAITS_PER_MESSAGE,
    TraitRow,
    count_components,
    render_part,
)
from org.models_leadership import CaptainTrait, EventCaptain, OrgLeadershipSettings
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
