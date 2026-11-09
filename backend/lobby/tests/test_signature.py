from django.test import SimpleTestCase

from lobby.webhook import sign, verify_signature

# dota_lobby's published test vector (docs/operations/webhooks.md).
VECTOR_SECRET = "whsec_test"
VECTOR_TS = "1762624800"
VECTOR_BODY = b'{"id":"evt_1"}'
VECTOR_SIG = "v1=898d18dde6b7357e818e3ae907e65e07b079679e0f30cb710a2f307c7e7ee5a0"
NOW = 1762624800.0


def _verify(
    secrets=(VECTOR_SECRET,), ts=VECTOR_TS, sig=VECTOR_SIG, body=VECTOR_BODY, now=NOW
):
    return verify_signature(secrets, ts, sig, body, tolerance_seconds=300, now=now)


class SignatureTests(SimpleTestCase):
    def test_dota_lobby_test_vector(self):
        self.assertEqual(sign(VECTOR_SECRET, VECTOR_TS, VECTOR_BODY), VECTOR_SIG)
        self.assertTrue(_verify())

    def test_rotation_list_in_header(self):
        other = sign("whsec_old", VECTOR_TS, VECTOR_BODY)
        self.assertTrue(_verify(sig=f"{other}, {VECTOR_SIG}"))
        self.assertTrue(_verify(sig=f"{VECTOR_SIG},{other}"))

    def test_rotation_list_in_settings(self):
        self.assertTrue(_verify(secrets=("whsec_new", VECTOR_SECRET)))

    def test_whitespace_around_values(self):
        self.assertTrue(_verify(ts=f" {VECTOR_TS} ", sig=f"  {VECTOR_SIG}  "))

    def test_wrong_secret(self):
        self.assertFalse(_verify(secrets=("whsec_other",)))

    def test_no_secrets(self):
        self.assertFalse(_verify(secrets=()))

    def test_body_changed(self):
        self.assertFalse(_verify(body=b'{"id":"evt_2"}'))

    def test_parsed_and_reserialized_body_fails(self):
        self.assertFalse(_verify(body=b'{"id": "evt_1"}'))

    def test_bad_timestamp(self):
        for ts in ("", None, "abc", "-1762624800", "1762624800.5"):
            with self.subTest(ts=ts):
                self.assertFalse(_verify(ts=ts))

    def test_clock_skew(self):
        self.assertTrue(_verify(now=NOW + 300))
        self.assertTrue(_verify(now=NOW - 300))
        self.assertFalse(_verify(now=NOW + 301))
        self.assertFalse(_verify(now=NOW - 301))

    def test_missing_or_other_version_signature(self):
        for sig in ("", None, ",", VECTOR_SIG.replace("v1=", "v2="), VECTOR_SIG[3:]):
            with self.subTest(sig=sig):
                self.assertFalse(_verify(sig=sig))
