from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from lobby.passwords import (
    ALPHABET,
    GENERATED_LENGTH,
    MAX_LENGTH,
    PasswordMode,
    generate_password,
    validate_password,
)


class GeneratePasswordTests(SimpleTestCase):
    def test_length_and_alphabet(self):
        for _ in range(50):
            password = generate_password()
            self.assertEqual(len(password), GENERATED_LENGTH)
            self.assertTrue(set(password) <= set(ALPHABET), password)

    def test_alphabet_has_no_ambiguous_characters(self):
        for ch in "ilo01IO":
            self.assertNotIn(ch, ALPHABET)

    def test_passwords_differ(self):
        self.assertEqual(len({generate_password() for _ in range(50)}), 50)

    def test_generated_passwords_are_valid(self):
        self.assertEqual(validate_password(p := generate_password()), p)


class ValidatePasswordTests(SimpleTestCase):
    def test_accepts_printable_ascii_up_to_the_limit(self):
        for value in ("a", "Team Night #4!", "x" * MAX_LENGTH, "a b~c"):
            with self.subTest(value=value):
                self.assertEqual(validate_password(value), value)

    def test_rejects(self):
        cases = {
            "": "required",
            "x" * (MAX_LENGTH + 1): "max_length",
            "pässword": "invalid_characters",
            "tab\there": "invalid_characters",
            "new\nline": "invalid_characters",
            " leading": "surrounding_spaces",
            "trailing ": "surrounding_spaces",
        }
        for value, code in cases.items():
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as ctx:
                    validate_password(value)
                self.assertEqual(ctx.exception.code, code)

    def test_modes(self):
        self.assertEqual(set(PasswordMode.values), {"fixed", "random"})
