import base64
import json
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from org.api_connections.crypto import (
    CredentialError,
    canonical_origin,
    open_credential,
    seal_credential,
)
from org.models import Organization, OrgApiConnection

OLD_KEY = {"id": "old", "key": base64.b64encode(b"o" * 32).decode()}
NEW_KEY = {"id": "new", "key": base64.b64encode(b"n" * 32).decode()}
BINDING = {"org_id": 12, "connection_id": 34, "origin": "https://example.com:443"}


class CredentialTests(SimpleTestCase):
    @override_settings(ORG_API_CREDENTIAL_KEYS="")
    def test_no_key_ring_fails_closed(self) -> None:
        with self.assertRaises(CredentialError) as caught:
            seal_credential("private-value", **BINDING)
        self.assertEqual(caught.exception.code, "credential_keys_unavailable")
        self.assertNotIn("private-value", str(caught.exception))

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_envelope_rejects_wrong_org_connection_origin_and_retired_key(self) -> None:
        envelope = seal_credential("private-value", **BINDING)
        self.assertNotIn("private-value", envelope)
        self.assertEqual(open_credential(envelope, **BINDING), "private-value")
        self.assertNotEqual(envelope, seal_credential("private-value", **BINDING))
        for changes in (
            {"org_id": 13},
            {"connection_id": 35},
            {"origin": "https://other.example:443"},
        ):
            with self.subTest(changes=changes), self.assertRaises(CredentialError):
                open_credential(envelope, **(BINDING | changes))
        for broken in (envelope[:-4] + "AAAA", "not-json", "{}"):
            with self.subTest(broken=broken), self.assertRaises(CredentialError):
                open_credential(broken, **BINDING)
        with override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY])):
            with self.assertRaises(CredentialError) as caught:
                open_credential(envelope, **BINDING)
            self.assertEqual(caught.exception.code, "credential_key_unavailable")

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_key_rotation_reads_old_and_writes_first_key(self) -> None:
        old = seal_credential("private-value", **BINDING)
        with override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY, OLD_KEY])):
            self.assertEqual(open_credential(old, **BINDING), "private-value")
            new = seal_credential("private-value", **BINDING)
        with override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY])):
            self.assertEqual(open_credential(new, **BINDING), "private-value")

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_maximum_utf8_secret_round_trips_and_rejects_oversize(self) -> None:
        secret = "é" * 4096
        envelope = seal_credential(secret, **BINDING)
        self.assertEqual(open_credential(envelope, **BINDING), secret)
        with self.assertRaises(CredentialError):
            seal_credential(secret + "x", **BINDING)

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def test_invalid_unicode_secret_has_a_fixed_error_code(self) -> None:
        with self.assertRaises(CredentialError) as caught:
            seal_credential("\ud800", **BINDING)
        self.assertEqual(caught.exception.code, "credential_invalid")

    def test_invalid_ring_is_not_partially_accepted(self) -> None:
        for ring in (
            [OLD_KEY, OLD_KEY],
            [{"id": "x", "key": "short"}],
            {"key": "wrong"},
            [OLD_KEY, {"id": "bad", "key": "!"}],
        ):
            with (
                self.subTest(ring=ring),
                override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps(ring)),
            ):
                with self.assertRaises(CredentialError):
                    seal_credential("private-value", **BINDING)

    def test_origin_is_canonical_and_rejects_ambiguous_urls(self) -> None:
        self.assertEqual(
            canonical_origin("https://EXAMPLE.com/path"), "https://example.com:443"
        )
        self.assertEqual(
            canonical_origin("https://bücher.example:8443/a"),
            "https://xn--bcher-kva.example:8443",
        )
        self.assertEqual(
            canonical_origin("https://[2606:4700::1111]/a"),
            "https://[2606:4700::1111]:443",
        )
        for value in (
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/#fragment",
            "https://example.com:bad",
            "https://example.com:0",
            "https://[2606:4700::1111%eth0]/",
            "https://example.com\\@evil.example",
            "https://example.com\n",
        ):
            with self.subTest(value=value), self.assertRaises(CredentialError):
                canonical_origin(value)


class ReencryptTests(TestCase):
    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([OLD_KEY]))
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Credential rotation")
        self.connection = OrgApiConnection.objects.create(
            organization=self.org,
            name="Remote",
            outbound_base_url="https://example.com",
            outbound_auth="bearer",
        )
        self.binding = {
            "org_id": self.org.pk,
            "connection_id": self.connection.pk,
            "origin": "https://example.com:443",
        }
        self.connection.outbound_credential_ciphertext = seal_credential(
            "rotation-secret", **self.binding
        )
        self.connection.outbound_credential_key_id = "old"
        self.connection.save()

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY, OLD_KEY]))
    def test_reencryption_rejects_swapped_origin_without_writing(self) -> None:
        original = self.connection.outbound_credential_ciphertext
        self.connection.outbound_base_url = "https://other.example"
        self.connection.save(update_fields=["outbound_base_url"])
        with self.assertRaises(CommandError) as caught:
            call_command("reencrypt_org_api_credentials", stdout=StringIO())
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.outbound_credential_ciphertext, original)
        self.assertEqual(self.connection.outbound_credential_key_id, "old")
        self.assertNotIn("rotation-secret", str(caught.exception))

    @override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY, OLD_KEY]))
    def test_dry_run_does_not_write_and_real_pass_verifies_mixed_keys(self) -> None:
        before = self.connection.outbound_credential_ciphertext
        current = OrgApiConnection.objects.create(
            organization=self.org,
            name="Current",
            outbound_base_url="https://example.com",
            outbound_auth="bearer",
        )
        binding = self.binding | {"connection_id": current.pk}
        current.outbound_credential_ciphertext = seal_credential(
            "current-secret", **binding
        )
        current.outbound_credential_key_id = "new"
        current.save()
        output = StringIO()
        call_command("reencrypt_org_api_credentials", dry_run=True, stdout=output)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.outbound_credential_ciphertext, before)
        call_command("reencrypt_org_api_credentials", stdout=output)
        with override_settings(ORG_API_CREDENTIAL_KEYS=json.dumps([NEW_KEY])):
            for connection, expected in (
                (self.connection, "rotation-secret"),
                (current, "current-secret"),
            ):
                connection.refresh_from_db()
                self.assertEqual(connection.outbound_credential_key_id, "new")
                self.assertEqual(
                    open_credential(
                        connection.outbound_credential_ciphertext,
                        **(self.binding | {"connection_id": connection.pk}),
                    ),
                    expected,
                )
        self.assertNotIn("secret", output.getvalue())
        self.assertEqual(self.connection.config_version, 1)
