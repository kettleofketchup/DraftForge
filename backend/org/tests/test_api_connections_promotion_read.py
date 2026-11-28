from typing import Any

from django.core import signing

from org.api_tokens.tokens import hash_secret, issue_token
from org.integration.contact_history import CURSOR_SALT
from org.models import OrgApiConnection, OrgApiToken, OrgApiTokenUsage
from org.models_promotion_sync import ExternalPromotionReceipt
from org.tests.test_integration_contacts import OCCASION, _ImportBase, age_import

ITEM_KEYS = {
    "receipt_id",
    "source_contact_id",
    "event_id",
    "discord_id",
    "contact_method",
    "contact_reason",
    "recorded_at",
    "retracted_at",
    "source_revision",
    "point_status",
}


class ContactHistoryTests(_ImportBase):
    def setUp(self) -> None:
        super().setUp()
        self.reader = issue_token(
            self.org, self.admin, "reader", operations=["promotion:read"]
        )

    def history(self, raw: str | None = None, **params: Any) -> Any:
        query = {"event_id": str(self.event.pk), **params}
        return self.bearer(raw or self.reader.raw).get(self.import_url(), query)

    def legacy_key(self, connection: OrgApiConnection, name: str) -> str:
        prefix, secret = f"legacy0{name}", f"secret-{name}"
        OrgApiToken.objects.create(
            connection=connection,
            organization=self.org,
            user=self.admin,
            name=name,
            prefix=prefix,
            secret_hash=hash_secret(secret),
            operations=["promotion:import"],
            legacy_credential=True,
        )
        return f"dfk_{prefix}_{secret}"

    def test_two_legacy_import_keys_share_history_without_conflict(self) -> None:
        connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Legacy promotion",
            enabled=True,
            inbound_enabled=True,
            operations=["promotion:import"],
            legacy_multi_credential=True,
        )
        first, second = (
            self.legacy_key(connection, "a"),
            self.legacy_key(connection, "b"),
        )
        self.imported([self.entry(8021, self.recipient)], raw=first)
        body = self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, self.recipient)],
            raw=second,
        )
        self.assertEqual(self.statuses(body), ["unchanged", "applied"])
        resp = self.history()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            [item["source_contact_id"] for item in resp.json()["items"]],
            ["8021", "8022"],
        )
        self.assertEqual(
            set(
                ExternalPromotionReceipt.objects.values_list("connection_id", flat=True)
            ),
            {connection.pk},
        )

    def test_import_only_never_gains_read(self) -> None:
        resp = self.history(self.issued.raw)
        self.assertError(resp, 403, "operation_not_granted")
        write = issue_token(self.org, self.admin, "w", operations=["promotion:write"])
        self.assertError(self.history(write.raw), 403, "operation_not_granted")
        reader_post = self.post([self.entry(8021, self.recipient)], raw=self.reader.raw)
        self.assertError(reader_post, 403, "operation_not_granted")
        self.assertFalse(ExternalPromotionReceipt.objects.exists())

    def test_write_or_import_budget_admitted_once(self) -> None:
        for index, operations in enumerate(
            (["promotion:write"], ["promotion:import", "promotion:write"])
        ):
            issued = issue_token(self.org, self.admin, "w", operations=operations)
            body = self.imported(
                [self.entry(8030 + index, self.recipient)], raw=issued.raw
            )
            self.assertEqual(self.statuses(body), ["applied"])
            self.assertEqual(
                OrgApiTokenUsage.objects.get(token=issued.token).request_count, 1
            )
            self.assertEqual(
                self.receipt(8030 + index).connection_id, issued.token.connection_id
            )

    def test_signed_history_cursor_cannot_cross_org_event_filter(self) -> None:
        self.imported([self.entry(i, self.recipient) for i in range(8021, 8024)])
        first = self.history(limit="2").json()
        self.assertEqual(len(first["items"]), 2)
        cursor = first["next_cursor"]
        self.assertIsNotNone(cursor)
        rest = self.history(limit="2", cursor=cursor).json()
        self.assertEqual([i["source_contact_id"] for i in rest["items"]], ["8023"])
        self.assertIsNone(rest["next_cursor"])
        for params in (
            {"limit": "3", "cursor": cursor},
            {"limit": "2", "cursor": cursor + "x"},
            {"limit": "2", "event_id": str(self.completed_event.pk), "cursor": cursor},
            {
                "limit": "2",
                "cursor": signing.dumps(
                    {"o": self.other_org.pk, "e": self.event.pk, "l": 2, "p": 0},
                    salt=CURSOR_SALT,
                ),
            },
        ):
            with self.subTest(params=params):
                self.assertError(self.history(**params), 400, "invalid_request")
        self.assertError(self.history(unknown="1"), 400, "invalid_request")
        self.assertError(self.history(limit="101"), 400, "invalid_request")
        self.assertError(self.history(limit="0"), 400, "invalid_request")
        missing = self.bearer(self.reader.raw).get(self.import_url())
        self.assertError(missing, 400, "invalid_request")
        self.assertError(
            self.bearer(self.reader.raw).get(self.import_url(), {"event_id": "999999"}),
            404,
            "not_found",
        )
        self.assertError(
            self.bearer(self.reader.raw).get(self.import_url(self.other_org)),
            404,
            "not_found",
        )

    def test_default_limit_is_one_hundred(self) -> None:
        self.imported([self.entry(i, self.recipient) for i in range(1, 101)])
        self.imported(
            [self.entry(i, self.recipient) for i in range(101, 103)], after=100
        )
        body = self.history().json()
        self.assertEqual(len(body["items"]), 100)
        self.assertIsNotNone(body["next_cursor"])

    def test_unbound_event_is_refused(self) -> None:
        self.bind({self.event: OCCASION})
        resp = self.history(event_id=str(self.completed_event.pk))
        self.assertError(resp, 403, "binding_missing")

    def test_history_projection_contains_tombstones_not_messages(self) -> None:
        self.imported(
            [self.entry(8021, self.recipient), self.entry(8022, self.recipient)]
        )
        age_import(self.receipt(8022).pk)
        self.imported(
            [self.entry(8021, self.recipient, contact_method="DISCORD_GROUP_DM")],
            after=8020,
            through=8022,
        )
        self.assertIsNotNone(self.receipt(8022).retracted_at)
        body = self.history().json()
        self.assertEqual(body["schema_version"], 1)
        self.assertEqual(set(body), {"schema_version", "items", "next_cursor"})
        by_id = {item["source_contact_id"]: item for item in body["items"]}
        for item in by_id.values():
            self.assertEqual(set(item), ITEM_KEYS)
            self.assertEqual(item["event_id"], str(self.event.pk))
        self.assertEqual(by_id["8021"]["contact_method"], "DISCORD_GROUP_DM")
        self.assertEqual(by_id["8021"]["source_revision"], 1)
        self.assertIsNotNone(by_id["8022"]["retracted_at"])
        text = str(body)
        self.assertNotIn(self.recipient.username, text)
        self.assertNotIn("Hi ", text)
