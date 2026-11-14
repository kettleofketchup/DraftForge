from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from app.models import CustomUser, League, Organization, Tournament
from events.constants import EventState
from events.models import Event
from org.features import FeatureKey, set_org_feature
from org.models import ContributionEntry, OrgUser, PromoSend, PromoTemplate
from org.promotion.render import PLACEHOLDERS
from org.promotion.services import record_promo_send
from org.promotion.starter import STARTER_TEMPLATE_NAME

ROLES = (
    "owner",
    "admin",
    "staff",
    "promoter",
    "member",
    "outsider",
    "site_admin",
    "anon",
)
PROMOTER_TIER = {"owner", "admin", "staff", "promoter", "site_admin"}
STAFF_TIER = {"owner", "admin", "staff", "site_admin"}


def base(org_id: int) -> str:
    return f"/api/organizations/{org_id}/promotion/"


class PromotionApiBase(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        self.users: dict[str, CustomUser | None] = {"anon": None}
        for role in ROLES[:-1]:
            self.users[role] = self._user(f"papi_{role}", is_staff=role == "site_admin")
        self.promoter_b = self._user("papi_promoter_b")
        self.org = Organization.objects.create(
            name="Promotion API Org", owner=self.users["owner"]
        )
        self.org.admins.add(self.users["admin"])
        self.org.staff.add(self.users["staff"])
        self.org.promoters.add(self.users["promoter"], self.promoter_b)
        OrgUser.objects.create(user=self.users["member"], organization=self.org)
        self.other_org = Organization.objects.create(
            name="Other Promotion Org", owner=self.users["owner"]
        )
        for org in (self.org, self.other_org):
            set_org_feature(org, FeatureKey.PROMOTION, enabled=True, actor=None)

        self.recipient = self._user("papi_recipient")
        self.recipient.guildNickname = "Recipient Guild"
        self.recipient.save()
        OrgUser.objects.create(user=self.recipient, organization=self.org)
        self.league = League.objects.create(
            name="Promotion API League", organization=self.org, steam_league_id=88401
        )
        past = Tournament.objects.create(
            name="Promotion API Past",
            date_played=now - timedelta(days=4),
            league=self.league,
        )
        past.users.add(self.recipient)
        self.event = Event.objects.create(
            organization=self.org,
            name="Promo Night",
            scheduled_at=now + timedelta(days=3),
            created_by=self.users["owner"],
            state=EventState.UPCOMING,
        )
        self.completed_event = Event.objects.create(
            organization=self.org,
            name="Old Night",
            scheduled_at=now - timedelta(days=3),
            created_by=self.users["owner"],
            state=EventState.COMPLETED,
        )
        self.template = PromoTemplate.objects.create(
            organization=self.org, name="Invite", body="Hi {player}, {event_time}"
        )
        self.other_event = Event.objects.create(
            organization=self.other_org,
            name="Other Night",
            scheduled_at=now + timedelta(days=3),
            created_by=self.users["owner"],
            state=EventState.UPCOMING,
        )
        self.other_template = PromoTemplate.objects.create(
            organization=self.other_org, name="Other", body="Hi"
        )
        self.client = APIClient()

    def _user(self, username: str, *, is_staff: bool = False) -> CustomUser:
        user = CustomUser.objects.create_user(
            username=username, password="x", is_staff=is_staff
        )
        user.discordId = str(884000000000000000 + user.pk)
        user.discordUsername = f"{username}_dc"
        user.save()
        return user

    def lock(self) -> None:
        set_org_feature(self.org, FeatureKey.PROMOTION, enabled=False, actor=None)

    def request(
        self,
        who: str | CustomUser,
        method: str,
        path: str,
        data: Any = None,
    ) -> Response:
        user = self.users[who] if isinstance(who, str) else who
        self.client.force_authenticate(user=user)
        if method == "get":
            return self.client.get(path, data)
        return getattr(self.client, method)(path, data, format="json")

    def assertCode(self, response: Response, code: str | None) -> None:
        self.assertEqual(response.status_code, 403, response.content)
        body = response.json()
        if code is None:
            self.assertNotIn("code", body)
        else:
            self.assertEqual(body.get("code"), code)

    def candidates_url(self, event: Event | None = None) -> str:
        return f"{base(self.org.pk)}events/{(event or self.event).pk}/candidates/"

    def sends_url(self, event: Event | None = None) -> str:
        return f"{base(self.org.pk)}events/{(event or self.event).pk}/sends/"

    def render_url(self, event: Event | None = None) -> str:
        return f"{base(self.org.pk)}events/{(event or self.event).pk}/render/"

    def send_as(self, sender: CustomUser) -> PromoSend:
        return record_promo_send(
            sender=sender,
            event=self.event,
            recipient=self.recipient,
            template=self.template,
            text="Hi",
        )


class PromotionPermissionMatrixTest(PromotionApiBase):
    def _read_endpoints(self) -> list[str]:
        url = base(self.org.pk)
        return [
            f"{url}placeholders/",
            f"{url}templates/",
            f"{url}events/",
            self.candidates_url(),
        ]

    def test_promoter_tier_can_read(self) -> None:
        for role in ROLES:
            for path in self._read_endpoints():
                with self.subTest(role=role, path=path):
                    response = self.request(role, "get", path)
                    if role in PROMOTER_TIER:
                        self.assertEqual(response.status_code, 200, response.content)
                    elif role == "anon":
                        self.assertCode(response, None)
                    else:
                        self.assertCode(response, "not_permitted")

    def test_locked_is_feature_locked_for_everyone(self) -> None:
        self.lock()
        for role in ROLES:
            for path in self._read_endpoints():
                with self.subTest(role=role, path=path):
                    self.assertCode(self.request(role, "get", path), "feature_locked")
            with self.subTest(role=role, write="send"):
                response = self.request(
                    role,
                    "post",
                    self.sends_url(),
                    {
                        "template_id": None,
                        "recipient_id": self.recipient.pk,
                        "text": "x",
                    },
                )
                self.assertCode(response, "feature_locked")

    def test_revoked_promoter_not_permitted(self) -> None:
        self.org.promoters.remove(self.users["promoter"])
        self.assertCode(
            self.request("promoter", "get", self.candidates_url()), "not_permitted"
        )

    def test_template_writes_need_staff(self) -> None:
        url = f"{base(self.org.pk)}templates/"
        detail = f"{url}{self.template.pk}/"
        for role in ROLES:
            with self.subTest(role=role):
                post = self.request(
                    role, "post", url, {"name": f"N {role}", "body": "Hi"}
                )
                patch = self.request(role, "patch", detail, {"name": f"P {role}"})
                if role in STAFF_TIER:
                    self.assertEqual(post.status_code, 201, post.content)
                    self.assertEqual(patch.status_code, 200, patch.content)
                elif role == "anon":
                    self.assertCode(post, None)
                    self.assertCode(patch, None)
                else:
                    self.assertCode(post, "not_permitted")
                    self.assertCode(patch, "not_permitted")
        self.assertCode(self.request("promoter", "delete", detail), "not_permitted")
        self.assertEqual(self.request("staff", "delete", detail).status_code, 204)
        self.assertFalse(PromoTemplate.objects.filter(pk=self.template.pk).exists())


class PromotionCrossOrgTest(PromotionApiBase):
    def test_cross_org_objects_404(self) -> None:
        url = base(self.org.pk)
        foreign_send = PromoSend.objects.create(
            organization=self.other_org,
            event=self.other_event,
            recipient=self.recipient,
            sender=self.users["owner"],
            text="Hi",
        )
        cases = [
            ("get", self.candidates_url(self.other_event), None),
            (
                "post",
                self.render_url(self.other_event),
                {"template_id": self.template.pk, "recipient_id": self.recipient.pk},
            ),
            (
                "post",
                self.render_url(),
                {
                    "template_id": self.other_template.pk,
                    "recipient_id": self.recipient.pk,
                },
            ),
            (
                "post",
                self.sends_url(self.other_event),
                {"template_id": None, "recipient_id": self.recipient.pk, "text": "x"},
            ),
            (
                "post",
                self.sends_url(),
                {
                    "template_id": self.other_template.pk,
                    "recipient_id": self.recipient.pk,
                    "text": "x",
                },
            ),
            ("patch", f"{url}templates/{self.other_template.pk}/", {"name": "x"}),
            ("delete", f"{url}templates/{self.other_template.pk}/", None),
            ("delete", f"{url}sends/{foreign_send.pk}/", None),
        ]
        for method, path, data in cases:
            with self.subTest(method=method, path=path, data=data):
                response = self.request("owner", method, path, data)
                self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(PromoSend.objects.filter(pk=foreign_send.pk).exists())
        self.assertTrue(
            PromoTemplate.objects.filter(pk=self.other_template.pk).exists()
        )

    def test_unknown_org_404(self) -> None:
        response = self.request("site_admin", "get", f"{base(999999)}templates/")
        self.assertEqual(response.status_code, 404)


class PromotionReadTest(PromotionApiBase):
    def test_placeholders(self) -> None:
        response = self.request("promoter", "get", f"{base(self.org.pk)}placeholders/")
        self.assertEqual(response.json(), [dict(p) for p in PLACEHOLDERS])

    def test_templates_list(self) -> None:
        response = self.request("promoter", "get", f"{base(self.org.pk)}templates/")
        rows = response.json()
        self.assertEqual(
            [r["name"] for r in rows], [STARTER_TEMPLATE_NAME, self.template.name]
        )
        self.assertNotIn(self.other_template.pk, [r["id"] for r in rows])
        self.assertEqual(set(rows[0]), {"id", "name", "body", "updated_at"})

    def test_template_create_returns_warnings(self) -> None:
        response = self.request(
            "staff",
            "post",
            f"{base(self.org.pk)}templates/",
            {"name": "Bad", "body": "Hi {player:>9} {"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(
            body["warnings"], ["unknown placeholder {player:>9}", "unbalanced brace"]
        )
        created = PromoTemplate.objects.get(pk=body["id"])
        self.assertEqual(created.organization_id, self.org.pk)
        self.assertEqual(created.created_by_id, self.users["staff"].pk)

    def test_template_body_over_limit_400(self) -> None:
        response = self.request(
            "staff",
            "post",
            f"{base(self.org.pk)}templates/",
            {"name": "Long", "body": "x" * 2001},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("body", response.json())

    def test_events_lists_promotable_only(self) -> None:
        response = self.request("promoter", "get", f"{base(self.org.pk)}events/")
        rows = response.json()
        self.assertEqual([r["id"] for r in rows], [self.event.pk])
        self.assertEqual(
            set(rows[0]),
            {"id", "name", "scheduled_at", "ends_at", "state", "signups_open_at"},
        )

    def test_candidates_expose_discord_username_only_here(self) -> None:
        response = self.request("promoter", "get", self.candidates_url(), {"n": "50"})
        body = response.json()
        self.assertEqual(body["n"], 10)
        self.assertEqual([r["user_pk"] for r in body["rows"]], [self.recipient.pk])
        self.assertEqual(body["rows"][0]["discordUsername"], "papi_recipient_dc")

        detail = self.request("owner", "get", f"/api/organizations/{self.org.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("discordUsername", detail.content.decode())
        users = self.request("owner", "get", f"/api/organizations/{self.org.pk}/users/")
        self.assertEqual(users.status_code, 200)
        self.assertIn("papi_recipient", users.content.decode())
        self.assertNotIn("discordUsername", users.content.decode())


class PromotionRenderAndSendTest(PromotionApiBase):
    def test_render_returns_discord_codes(self) -> None:
        response = self.request(
            "promoter",
            "post",
            self.render_url(),
            {"template_id": self.template.pk, "recipient_id": self.recipient.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        stamp = int(self.event.scheduled_at.timestamp())
        self.assertEqual(body["text"], f"Hi Recipient Guild, <t:{stamp}:F>")
        self.assertEqual(body["warnings"], [])
        self.assertTrue(body["will_earn"])

    def test_render_rejects_recipient_outside_pool(self) -> None:
        response = self.request(
            "promoter",
            "post",
            self.render_url(),
            {"template_id": self.template.pk, "recipient_id": self.promoter_b.pk},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("recipient_id", response.json())

    def test_render_rejects_completed_event(self) -> None:
        response = self.request(
            "promoter",
            "post",
            self.render_url(self.completed_event),
            {"template_id": self.template.pk, "recipient_id": self.recipient.pk},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("event", response.json())

    def test_render_rejects_self(self) -> None:
        promoter = self.users["promoter"]
        Tournament.objects.get(name="Promotion API Past").users.add(promoter)
        response = self.request(
            "promoter",
            "post",
            self.render_url(),
            {"template_id": self.template.pk, "recipient_id": promoter.pk},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("recipient_id", response.json())

    def test_render_as_roleless_site_admin_will_not_earn(self) -> None:
        response = self.request(
            "site_admin",
            "post",
            self.render_url(),
            {"template_id": self.template.pk, "recipient_id": self.recipient.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["will_earn"])

    def test_send_then_send_again_flips_earns_points(self) -> None:
        payload = {
            "template_id": self.template.pk,
            "recipient_id": self.recipient.pk,
            "text": "Hi Recipient",
        }
        first = self.request("promoter", "post", self.sends_url(), payload)
        self.assertEqual(first.status_code, 201, first.content)
        first_body = first.json()
        self.assertTrue(first_body["earns_points"])
        self.assertIsNone(first_body["points_awarded"])
        self.assertEqual(
            set(first_body), {"id", "earns_points", "points_awarded", "sent_at"}
        )
        send = PromoSend.objects.get(pk=first_body["id"])
        self.assertEqual(send.sender_id, self.users["promoter"].pk)
        self.assertEqual(send.text, "Hi Recipient")

        render = self.request(
            self.promoter_b,
            "post",
            self.render_url(),
            {"template_id": self.template.pk, "recipient_id": self.recipient.pk},
        )
        self.assertFalse(render.json()["will_earn"])

        second = self.request(self.promoter_b, "post", self.sends_url(), payload)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertFalse(second.json()["earns_points"])
        self.assertIsNone(second.json()["points_awarded"])
        self.assertEqual(
            ContributionEntry.objects.nocache().filter(event=self.event).count(), 1
        )

    def test_send_reports_points_only_with_contributions_unlocked(self) -> None:
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=None)
        payload = {
            "template_id": self.template.pk,
            "recipient_id": self.recipient.pk,
            "text": "Hi Recipient",
        }
        first = self.request("promoter", "post", self.sends_url(), payload)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertTrue(first.json()["earns_points"])
        self.assertEqual(first.json()["points_awarded"], 1)

        second = self.request(self.promoter_b, "post", self.sends_url(), payload)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertFalse(second.json()["earns_points"])
        self.assertIsNone(second.json()["points_awarded"])

    def test_send_without_template(self) -> None:
        response = self.request(
            "promoter",
            "post",
            self.sends_url(),
            {"template_id": None, "recipient_id": self.recipient.pk, "text": "Yo"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(PromoSend.objects.get(pk=response.json()["id"]).template_id)

    def test_send_validation_error_shape(self) -> None:
        cases = [
            (
                self.event,
                {"recipient_id": self.promoter_b.pk, "text": "x"},
                "recipient_id",
            ),
            (
                self.completed_event,
                {"recipient_id": self.recipient.pk, "text": "x"},
                "event",
            ),
            (
                self.event,
                {"recipient_id": self.recipient.pk, "text": "x" * 4001},
                "text",
            ),
            (self.event, {"recipient_id": 999999, "text": "x"}, "recipient_id"),
        ]
        for event, payload, field in cases:
            with self.subTest(field=field, event=event.pk):
                response = self.request(
                    "promoter",
                    "post",
                    self.sends_url(event),
                    {"template_id": None, **payload},
                )
                self.assertEqual(response.status_code, 400, response.content)
                body = response.json()
                self.assertIn(field, body)
                self.assertIsInstance(body[field], list)
        self.assertFalse(PromoSend.objects.exists())


class PromotionUndoTest(PromotionApiBase):
    def _row(self, viewer: str | CustomUser) -> dict[str, Any]:
        response = self.request(
            viewer, "get", self.candidates_url(), {"hide_messaged": "false"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = [r for r in response.json()["rows"] if r["user_pk"] == self.recipient.pk]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_messaged_hidden_by_default(self) -> None:
        self.send_as(self.users["promoter"])
        response = self.request("promoter", "get", self.candidates_url())
        self.assertEqual(response.json()["rows"], [])

    def test_can_undo_per_viewer_and_staff_undo(self) -> None:
        send = self.send_as(self.users["promoter"])
        staff_row = self._row("staff")
        self.assertEqual(staff_row["last_messaged"]["send_id"], send.pk)
        self.assertTrue(staff_row["last_messaged"]["can_undo"])
        self.assertFalse(self._row(self.promoter_b)["last_messaged"]["can_undo"])
        self.assertTrue(self._row("promoter")["last_messaged"]["can_undo"])

        denied = self.request(
            self.promoter_b, "delete", f"{base(self.org.pk)}sends/{send.pk}/"
        )
        self.assertCode(denied, "not_permitted")
        self.assertTrue(PromoSend.objects.filter(pk=send.pk).exists())

        response = self.request(
            "staff", "delete", f"{base(self.org.pk)}sends/{send.pk}/"
        )
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(PromoSend.objects.filter(pk=send.pk).exists())
        self.assertFalse(
            ContributionEntry.objects.nocache().filter(event=self.event).exists()
        )

    def test_sender_can_undo_own_send(self) -> None:
        send = self.send_as(self.users["promoter"])
        response = self.request(
            "promoter", "delete", f"{base(self.org.pk)}sends/{send.pk}/"
        )
        self.assertEqual(response.status_code, 204, response.content)
