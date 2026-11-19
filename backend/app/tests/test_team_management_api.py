"""Team management API (#545)."""

from typing import Any

from django.test import TestCase

from app.serializers import (
    TeamActionRequestSerializer,
    TeamDeputyRequestSerializer,
    TeamRenameRequestSerializer,
    TeamSubInRequestSerializer,
    TeamUserActionRequestSerializer,
)
from app.tests.test_team_management import TeamManagementFixture
from events.overrides import REASON_MAX_LENGTH, OverrideReasonRequired


class TeamActionRequestSerializerTests(TeamManagementFixture, TestCase):
    def user_body(self, **extra: Any) -> dict[str, Any]:
        return {"user_id": self.m1.pk, **extra}

    def test_reason_trimmed(self) -> None:
        body = TeamUserActionRequestSerializer(
            data=self.user_body(reason="  late swap  ")
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(body.validated_data["reason"], "late swap")
        self.assertEqual(body.validated_data["acknowledged_codes"], [])
        self.assertEqual(body.validated_data["user_id"], self.m1)

    def test_missing_blank_whitespace_reason_is_field_error(self) -> None:
        cases: list[dict[str, Any]] = [
            self.user_body(),
            self.user_body(reason=""),
            self.user_body(reason="   "),
            self.user_body(reason=None),
        ]
        for data in cases:
            with self.subTest(data=data):
                body = TeamUserActionRequestSerializer(data=data)
                self.assertFalse(body.is_valid())
                self.assertIn("reason", body.errors)

    def test_reason_too_long_is_field_error(self) -> None:
        long_reason = "x" * (REASON_MAX_LENGTH + 1)
        for codes in ([], ["team_standin_cap"]):
            with self.subTest(codes=codes):
                body = TeamUserActionRequestSerializer(
                    data=self.user_body(reason=long_reason, acknowledged_codes=codes)
                )
                self.assertFalse(body.is_valid())
                self.assertIn("reason", body.errors)

    def test_blank_reason_with_codes_raises_override_reason_required(self) -> None:
        body = TeamUserActionRequestSerializer(
            data=self.user_body(reason=" ", acknowledged_codes=["team_standin_cap"])
        )
        with self.assertRaises(OverrideReasonRequired):
            body.is_valid(raise_exception=True)

    def test_base_serializer_has_reason_and_codes_only(self) -> None:
        body = TeamActionRequestSerializer(
            data={"reason": "r", "acknowledged_codes": ["team_standin_cap"]}
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(
            dict(body.validated_data),
            {"reason": "r", "acknowledged_codes": ["team_standin_cap"]},
        )

    def test_unknown_user_id_is_field_error(self) -> None:
        for user_id in (999999, "abc"):
            with self.subTest(user_id=user_id):
                body = TeamUserActionRequestSerializer(
                    data={"user_id": user_id, "reason": "r"}
                )
                self.assertFalse(body.is_valid())
                self.assertIn("user_id", body.errors)

    def test_acknowledged_codes_must_be_list(self) -> None:
        too_many = [f"code_{i}" for i in range(101)]
        for codes in ("team_standin_cap", too_many):
            with self.subTest(codes=type(codes).__name__):
                body = TeamUserActionRequestSerializer(
                    data=self.user_body(reason="r", acknowledged_codes=codes)
                )
                self.assertFalse(body.is_valid())
                self.assertIn("acknowledged_codes", body.errors)

    def test_deputy_null_allowed_but_required(self) -> None:
        body = TeamDeputyRequestSerializer(data={"user_id": None, "reason": "r"})
        self.assertTrue(body.is_valid(), body.errors)
        self.assertIsNone(body.validated_data["user_id"])

        missing = TeamDeputyRequestSerializer(data={"reason": "r"})
        self.assertFalse(missing.is_valid())
        self.assertIn("user_id", missing.errors)

    def test_sub_in_replacing_optional(self) -> None:
        body = TeamSubInRequestSerializer(
            data={"standin_id": self.o1.pk, "reason": "r"}
        )
        self.assertTrue(body.is_valid(), body.errors)
        self.assertEqual(body.validated_data["standin_id"], self.o1)
        self.assertIsNone(body.validated_data["replacing_id"])

        both = TeamSubInRequestSerializer(
            data={"standin_id": self.o1.pk, "replacing_id": self.m2.pk, "reason": "r"}
        )
        self.assertTrue(both.is_valid(), both.errors)
        self.assertEqual(both.validated_data["replacing_id"], self.m2)

        missing = TeamSubInRequestSerializer(data={"reason": "r"})
        self.assertFalse(missing.is_valid())
        self.assertIn("standin_id", missing.errors)

    def test_rename_blank_name_reaches_service(self) -> None:
        for name in ("", "   ", "  padded  "):
            with self.subTest(name=name):
                body = TeamRenameRequestSerializer(data={"name": name, "reason": "r"})
                self.assertTrue(body.is_valid(), body.errors)
                self.assertEqual(body.validated_data["name"], name)
