from django.conf import settings
from django.test import SimpleTestCase

from user.models import DotaUserProfile, PositionsModel, ProfileClaimRequest


class UserModelConfigTest(SimpleTestCase):
    def test_labels_and_tables(self) -> None:
        self.assertEqual(
            [
                (m._meta.label, m._meta.db_table)
                for m in (PositionsModel, ProfileClaimRequest)
            ],
            [
                ("user.PositionsModel", "app_positionsmodel"),
                ("user.ProfileClaimRequest", "app_profileclaimrequest"),
            ],
        )

    def test_claim_request_index_and_constraint_names(self) -> None:
        meta = ProfileClaimRequest._meta
        self.assertEqual(
            [i.name for i in meta.indexes],
            ["app_profile_organiz_4b1a91_idx", "app_profile_claimer_2ce297_idx"],
        )
        self.assertEqual(
            [c.name for c in meta.constraints], ["unique_pending_claim_request"]
        )

    def test_positions_fk_target(self) -> None:
        field = DotaUserProfile._meta.get_field("positions")
        self.assertIs(field.related_model, PositionsModel)
        self.assertIsNone(field.remote_field.related_name)
        self.assertEqual(field.related_query_name(), "dotauserprofile")
        self.assertTrue(hasattr(PositionsModel, "dotauserprofile_set"))

    def test_claim_request_fk_targets(self) -> None:
        meta = ProfileClaimRequest._meta
        self.assertEqual(
            {
                name: meta.get_field(name).related_model._meta.label
                for name in ("claimer", "target_user", "reviewed_by", "organization")
            },
            {
                "claimer": settings.AUTH_USER_MODEL,
                "target_user": settings.AUTH_USER_MODEL,
                "reviewed_by": settings.AUTH_USER_MODEL,
                "organization": "org.Organization",
            },
        )
        self.assertEqual(
            meta.get_field("organization").remote_field.related_name,
            "claim_requests",
        )

    def test_no_cacheops_keys(self) -> None:
        for label in ("app", "user"):
            for model in ("positionsmodel", "profileclaimrequest"):
                self.assertNotIn(f"{label}.{model}", settings.CACHEOPS)
