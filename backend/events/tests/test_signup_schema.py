from django.test import SimpleTestCase
from pydantic import ValidationError as PydanticValidationError

from events.schemas import SignupInputPatch


class SignupInputPatchTest(SimpleTestCase):
    def test_empty_patch_parses(self) -> None:
        patch = SignupInputPatch()
        self.assertEqual(patch.model_dump(exclude_unset=True), {})

    def test_full_patch_parses(self) -> None:
        patch = SignupInputPatch(
            unverified_friend_id="12345678",
            positions=[1, 2, 3],
            rank_status="active",
            rank_medal="Crusader 3",
            rank_screenshot="https://i.imgur.com/abc.png",
        )
        self.assertEqual(patch.rank_status, "active")
        self.assertEqual(patch.positions, [1, 2, 3])

    def test_rank_status_rejects_invalid(self) -> None:
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(rank_status="bogus")

    def test_battle_cup_tier_range(self) -> None:
        SignupInputPatch(battle_cup_tier=8)
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(battle_cup_tier=9)
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(battle_cup_tier=0)

    def test_positions_range(self) -> None:
        SignupInputPatch(positions=[1, 5])
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(positions=[0])
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(positions=[6])

    def test_extra_fields_rejected(self) -> None:
        with self.assertRaises(PydanticValidationError):
            SignupInputPatch(unknown_field="x")
