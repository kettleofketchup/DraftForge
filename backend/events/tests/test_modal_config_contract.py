"""Contract tests for the #268 PR2 discriminated `modal_config` envelope.

Written as SimpleTestCase (no DB) so they run under the canonical
`manage.py test` runner that CI uses — the def-style pytest tests in
test_signup_schema.py are not collected by manage.py test.
"""

from django.test import SimpleTestCase

from events.schemas import (
    DeadlockModalConfig,
    DotaModalConfig,
    SignupActionResponse,
    SignupModalConfig,
    dota_require_screenshot,
)


class ModalConfigKindTest(SimpleTestCase):
    def test_dota_kind_and_fields(self):
        cfg = DotaModalConfig(min_mmr=3000, allow_active_mmr=False)
        self.assertEqual(cfg.kind, "dota")
        self.assertEqual(cfg.min_mmr, 3000)
        self.assertFalse(cfg.allow_active_mmr)

    def test_deadlock_kind(self):
        self.assertEqual(DeadlockModalConfig().kind, "deadlock")

    def test_base_kind_default(self):
        self.assertEqual(SignupModalConfig().kind, "default")


class DotaRequireScreenshotTest(SimpleTestCase):
    def test_truth_table(self):
        on = DotaModalConfig(
            require_rank_screenshot=True, require_battlecup_screenshot=True
        )
        self.assertTrue(dota_require_screenshot("active", on))
        self.assertTrue(dota_require_screenshot("never", on))
        self.assertFalse(dota_require_screenshot("previous", on))

        off = DotaModalConfig(
            require_rank_screenshot=False, require_battlecup_screenshot=False
        )
        self.assertFalse(dota_require_screenshot("active", off))
        self.assertFalse(dota_require_screenshot("never", off))


class SignupActionResponseContractTest(SimpleTestCase):
    def test_modal_config_survives_validate_then_dump(self):
        """Wire path is model_validate(dict).model_dump() in signup_actions.py.

        A plain base annotation would serialize-as-base and drop the Dota
        fields; the kind-discriminated union keeps them.
        """
        resp = SignupActionResponse(
            action="needs_modal",
            game_type=1,
            modal_config=DotaModalConfig(min_mmr=2500, require_rank_screenshot=True),
        )
        rt = SignupActionResponse.model_validate(resp.model_dump()).model_dump()
        self.assertEqual(rt["modal_config"]["kind"], "dota")
        self.assertEqual(rt["modal_config"]["min_mmr"], 2500)
        self.assertTrue(rt["modal_config"]["require_rank_screenshot"])

    def test_deadlock_config_round_trips_as_deadlock(self):
        resp = SignupActionResponse(
            action="needs_modal", game_type=2, modal_config=DeadlockModalConfig()
        )
        rt = SignupActionResponse.model_validate(resp.model_dump())
        self.assertIsInstance(rt.modal_config, DeadlockModalConfig)

    def test_forbids_legacy_flat_keys(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            SignupActionResponse.model_validate(
                {"action": "needs_modal", "game_type": 1, "min_mmr": 3000}
            )

    def test_screenshot_type_stays_flat(self):
        resp = SignupActionResponse(action="needs_screenshot", screenshot_type="rank")
        rt = SignupActionResponse.model_validate(resp.model_dump())
        self.assertEqual(rt.screenshot_type, "rank")
