from typing import get_args

from django.test import SimpleTestCase

from events.schemas import _RANK_STATUS_ALLOW_FLAGS, DotaModalConfig, SignupInputPatch
from events.services import RANK_STATUS_DISALLOWED_MESSAGES
from org.models_profiles import PlayerDotaProfile


class RankStatusVocabularyParityTest(SimpleTestCase):
    def test_every_rank_status_table_matches_the_model_choices(self) -> None:
        statuses = set(PlayerDotaProfile.RANK_STATUSES)
        literal = SignupInputPatch.model_fields["rank_status"].annotation
        patch_values = {v for arg in get_args(literal) for v in get_args(arg)}

        self.assertEqual(set(_RANK_STATUS_ALLOW_FLAGS), statuses)
        self.assertEqual(set(RANK_STATUS_DISALLOWED_MESSAGES), statuses)
        self.assertEqual(patch_values, statuses)

    def test_allow_flags_name_real_config_fields(self) -> None:
        for flag in _RANK_STATUS_ALLOW_FLAGS.values():
            self.assertIn(flag, DotaModalConfig.model_fields)
