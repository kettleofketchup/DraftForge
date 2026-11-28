import json
from copy import deepcopy

from django.test import SimpleTestCase, TestCase, override_settings

from app.models import CustomUser
from org.api_connections.config import apply_config_patch
from org.api_connections.crypto import open_credential
from org.api_connections.schemas import (
    ConnectionConfigError,
    validate_connection_config,
)
from org.models import Organization, OrgApiConnection
from org.tests.test_api_connections_crypto import OLD_KEY


def pull_config() -> dict[str, object]:
    return {
        "outbound_base_url": "https://example.com",
        "mmr_pull_config": {
            "path": "/ratings/{org_id}/{game_type}",
            "method": "POST",
            "query": {"org": "{{org.id}}"},
            "body": {"players": "{{players.steam64_ids}}"},
            "mapping": {
                "list_path": "data.players",
                "player_id_path": "id",
                "player_id_type": "steam64",
                "mmr_path": "rating",
            },
            "pagination": {"kind": "page", "start": 0, "page_size": 500},
        },
    }


class ConfigValidationTests(SimpleTestCase):
    def assert_invalid(
        self, value: dict[str, object], code: str = "invalid_config"
    ) -> None:
        with self.assertRaises(ConnectionConfigError) as caught:
            validate_connection_config(value)
        self.assertEqual(caught.exception.code, code)

    def test_defaults_are_disabled_and_typed(self) -> None:
        config = validate_connection_config({})
        self.assertFalse(config.enabled)
        self.assertFalse(config.mark_verified)
        self.assertEqual(
            config.mmr_push_config.path, "/api/v1/organizations/{org_id}/mmr"
        )
        self.assertEqual(config.operations, [])
        self.assertEqual(
            validate_connection_config(
                pull_config()
            ).mmr_pull_config.mapping.player_id_type,
            "steam64",
        )

    def test_secret_like_literals_and_unknown_template_paths_rejected(self) -> None:
        for key in (
            "api_key",
            "API-KEY",
            "apikey",
            "key",
            "token",
            "Access-Token",
            "secret",
            "password",
            "auth",
            "authorization",
            "signature",
            "sig",
        ):
            for location in ("query", "body"):
                config = pull_config()
                config["mmr_pull_config"][location] = {key: "sensitive-value"}
                self.assert_invalid(config, "secret_like_literal")
        for template in (
            "{{unknown}}",
            "{{org.name}}",
            "{{players.__class__}}",
            "{{org.id + 1}}",
            "prefix-{{org.id}}",
            "{{credential}}",
        ):
            config = pull_config()
            config["mmr_pull_config"]["query"] = {"x": template}
            self.assert_invalid(config)
        for extra in (
            {"headers": {"Host": "evil.example"}},
            {"code": "return 1"},
            {"path": "https://evil.example"},
            {"path": "//evil.example"},
            {"path": "/{{player.discord_id}}"},
        ):
            config = pull_config()
            config["mmr_pull_config"].update(extra)
            self.assert_invalid(config)
        self.assert_invalid({"outbound_base_url": "https://{{org.id}}.example"})

    def test_api_key_field_requires_one_designated_secret_slot(self) -> None:
        config = pull_config()
        config["outbound_auth"] = "api_key_field"
        config["mmr_pull_config"]["credential_field"] = {
            "location": "query",
            "key": "api_key",
        }
        config["mmr_pull_config"]["query"]["api_key"] = "{{credential}}"
        self.assertEqual(
            validate_connection_config(config).outbound_auth, "api_key_field"
        )
        duplicate = deepcopy(config)
        duplicate["mmr_pull_config"]["body"]["other"] = "{{credential}}"
        self.assert_invalid(duplicate)
        config["mmr_pull_config"]["credential_field"]["key"] = "absent"
        self.assert_invalid(config)

    def test_push_field_auth_does_not_require_unused_pull_configuration(self) -> None:
        config = {
            "outbound_auth": "api_key_field",
            "outbound_base_url": "https://example.com",
            "mmr_push_config": {
                "query": {"api_key": "{{credential}}"},
                "credential_field": {"location": "query", "key": "api_key"},
            },
            "mmr_pull_config": {},
        }
        self.assertEqual(
            validate_connection_config(config).outbound_auth, "api_key_field"
        )

    def test_push_field_auth_supports_only_the_designated_body_credential(self) -> None:
        config = {
            "outbound_auth": "api_key_field",
            "outbound_base_url": "https://example.com",
            "mmr_push_config": {
                "body": {"api_key": "{{credential}}"},
                "credential_field": {"location": "body", "key": "api_key"},
            },
        }
        self.assertEqual(
            validate_connection_config(
                config
            ).mmr_push_config.credential_field.location,
            "body",
        )
        config["mmr_push_config"]["body"]["revision"] = 123
        self.assert_invalid(config)

    def test_config_bounds(self) -> None:
        for patch in (
            {"enabled": 1},
            {"enabled": "false"},
            {"enabled": None},
            {"interval_minutes": True},
            {"interval_minutes": 14},
            {"interval_minutes": 10081},
            {"game_type": True},
            {"mark_verified": 0},
            {"outbound_auth": "custom"},
            {"overwrite_policy": "newest"},
            {"headers": {}},
            {"operations": ["unknown"]},
        ):
            self.assert_invalid(patch)
        for interval in (None, 15, 10080):
            self.assertEqual(
                validate_connection_config(
                    {"interval_minutes": interval}
                ).interval_minutes,
                interval,
            )
        for patch in (
            {"method": "GET"},
            {"mapping": {"player_id_type": "discord"}},
            {"pagination": {"kind": "page", "start": 2}},
            {"pagination": {"kind": "page", "page_size": 501}},
            {"pagination": {"kind": "page", "page_size": True}},
            {"pagination": {"kind": "page", "page_size": 0}},
            {"mapping": {"list_path": "a." * 8 + "a"}},
            {"mapping": {"list_path": "a" * 257}},
            {"mapping": {"list_path": "a[*]"}},
            {"mapping": {"list_path": "a..b"}},
        ):
            config = pull_config()
            config["mmr_pull_config"].update(patch)
            self.assert_invalid(config)
        config = pull_config()
        config["mmr_pull_config"]["body"] = {str(i): "{{org.id}}" for i in range(101)}
        self.assert_invalid(config, "config_too_large")
        config["mmr_pull_config"]["body"] = {"value": "x" * 32768}
        self.assert_invalid(config, "config_too_large")
        for id_type in ("steam_account_id", "steam64", "discord_id"):
            config = pull_config()
            config["mmr_pull_config"]["mapping"]["player_id_type"] = id_type
            validate_connection_config(config)


@override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
class ConfigPatchTests(TestCase):
    def setUp(self) -> None:
        self.user = CustomUser.objects.create(username="config_admin")
        self.org = Organization.objects.create(name="Config test")
        self.org.admins.add(self.user)
        self.connection = OrgApiConnection.objects.create(
            organization=self.org, name="Remote"
        )

    def patch(
        self, patch: dict[str, object], version: int | None = None
    ) -> OrgApiConnection:
        return apply_config_patch(
            self.connection,
            actor=self.user,
            patch=patch,
            expected_version=version or self.connection.config_version,
        )

    def test_origin_edit_requires_replacement_or_explicit_clear(self) -> None:
        self.connection = self.patch(
            {
                "outbound_base_url": "https://example.com",
                "outbound_auth": "bearer",
                "outbound_credential": "top-secret",
            }
        )
        ciphertext = self.connection.outbound_credential_ciphertext
        self.connection = self.patch(
            {"outbound_base_url": "https://EXAMPLE.com:443/new"}
        )
        self.assertEqual(self.connection.outbound_credential_ciphertext, ciphertext)
        with self.assertRaises(ConnectionConfigError) as caught:
            self.patch({"outbound_base_url": "https://other.example"})
        self.assertEqual(caught.exception.code, "credential_required_for_new_origin")
        with self.assertRaises(ConnectionConfigError):
            self.patch(
                {"outbound_credential": "new-secret", "clear_outbound_credential": True}
            )
        self.connection = self.patch(
            {
                "outbound_base_url": "https://other.example",
                "outbound_credential": "new-secret",
            }
        )
        self.assertEqual(
            open_credential(
                self.connection.outbound_credential_ciphertext,
                org_id=self.org.pk,
                connection_id=self.connection.pk,
                origin="https://other.example:443",
            ),
            "new-secret",
        )
        self.connection = self.patch(
            {
                "outbound_base_url": "https://third.example",
                "clear_outbound_credential": True,
            }
        )
        self.assertEqual(self.connection.outbound_credential_ciphertext, "")
        self.assertIsNone(self.connection.outbound_credential_owner_id)
        self.assertIsNone(self.connection.outbound_credential_set_at)

    def test_credential_replace_and_clear_fields_are_mutually_exclusive(self) -> None:
        with self.assertRaises(ConnectionConfigError):
            self.patch(
                {
                    "outbound_base_url": "https://example.com",
                    "outbound_auth": "bearer",
                    "outbound_credential": "secret-value",
                    "clear_outbound_credential": False,
                }
            )
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.config_version, 1)
        self.assertEqual(self.connection.outbound_credential_ciphertext, "")

    def test_stale_version_rejected_and_invalid_patch_is_atomic(self) -> None:
        self.connection = self.patch({"name": "Changed"}, version=1)
        self.assertEqual(self.connection.config_version, 2)
        with self.assertRaises(ConnectionConfigError) as caught:
            self.patch({"name": "Stale"}, version=1)
        self.assertEqual(caught.exception.code, "configuration_changed")
        with self.assertRaises(ConnectionConfigError):
            self.patch({"name": "Bad", "interval_minutes": True})
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.name, "Changed")
        self.assertEqual(self.connection.config_version, 2)

    @override_settings(ORG_API_CREDENTIAL_KEYS="")
    def test_missing_keys_leave_inbound_only_configuration_usable(self) -> None:
        self.connection = self.patch({"name": "Inbound", "operations": ["mmr:read"]})
        self.assertEqual(self.connection.operations, ["mmr:read"])

    def test_auth_none_scrubs_secret_and_omission_keeps_owner(self) -> None:
        self.connection = self.patch(
            {
                "outbound_base_url": "https://example.com",
                "outbound_auth": "bearer",
                "outbound_credential": "top-secret",
            }
        )
        self.connection = self.patch({"name": "Renamed"})
        self.assertEqual(self.connection.outbound_credential_owner_id, self.user.pk)
        self.connection = self.patch({"outbound_auth": "none"})
        self.assertEqual(self.connection.outbound_credential_ciphertext, "")
        self.assertIsNone(self.connection.outbound_credential_owner_id)
        self.assertIsNone(self.connection.outbound_authorizer_id)
