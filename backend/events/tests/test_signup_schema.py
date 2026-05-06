from pydantic import ValidationError as PydanticValidationError
import pytest

from events.schemas import SignupInputPatch


def test_empty_patch_parses():
    patch = SignupInputPatch()
    assert patch.model_dump(exclude_unset=True) == {}


def test_full_patch_parses():
    patch = SignupInputPatch(
        unverified_friend_id="12345678",
        positions=[1, 2, 3],
        rank_status="active",
        rank_medal="Crusader 3",
        rank_screenshot="https://i.imgur.com/abc.png",
    )
    assert patch.rank_status == "active"
    assert patch.positions == [1, 2, 3]


def test_rank_status_rejects_invalid():
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(rank_status="bogus")


def test_battle_cup_tier_range():
    SignupInputPatch(battle_cup_tier=8)
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(battle_cup_tier=9)
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(battle_cup_tier=0)


def test_positions_range():
    SignupInputPatch(positions=[1, 5])
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(positions=[0])
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(positions=[6])


def test_extra_fields_rejected():
    with pytest.raises(PydanticValidationError):
        SignupInputPatch(unknown_field="x")
