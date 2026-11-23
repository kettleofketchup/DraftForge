from collections.abc import Callable

from django.test import TestCase

from events.constants import ActorRole, SignupAction, SignupMeans
from events.models import Event, EventSignup, SignupLedgerEntry
from tests.data.dota_lobby import LOBBY_ORG
from tests.data.game_org_mmr import GAME_MMR_ORG
from tests.data.org_features import ORG_FEATURES_ORGS
from tests.populate.dota_lobby import populate_dota_lobby_data
from tests.populate.game_org_mmr import populate_game_org_mmr_data
from tests.populate.org_features import populate_org_features_data


def _orphans() -> list[int]:
    return list(
        SignupLedgerEntry.objects.exclude(
            event_id__in=Event.objects.nocache().values("pk")
        ).values_list("pk", flat=True)
    ) + list(
        SignupLedgerEntry.objects.exclude(signup_id=None)
        .exclude(signup_id__in=EventSignup.objects.nocache().values("pk"))
        .values_list("pk", flat=True)
    )


def _ledger_every_event(org_names: list[str]) -> int:
    events = list(Event.objects.nocache().filter(organization__name__in=org_names))
    for event in events:
        signup = EventSignup.objects.nocache().filter(event=event).first()
        SignupLedgerEntry.objects.create(
            event=event,
            organization_id=event.organization_id,
            signup=signup,
            event_snapshot={"id": event.pk},
            subject_snapshot={"user_id": None},
            actor_role=ActorRole.SYSTEM,
            means=SignupMeans.SYSTEM,
            action=SignupAction.SIGNED_UP,
        )
    return len(events)


class PopulateLeavesNoLedgerOrphansTest(TestCase):
    def _assert_repopulate_clean(
        self, populate: Callable[..., None], org_names: list[str]
    ) -> None:
        populate(force=True)
        self.assertGreater(_ledger_every_event(org_names), 0)
        populate(force=True)
        self.assertEqual(_orphans(), [])

    def test_game_org_mmr(self) -> None:
        self._assert_repopulate_clean(populate_game_org_mmr_data, [GAME_MMR_ORG.name])

    def test_org_features(self) -> None:
        self._assert_repopulate_clean(
            populate_org_features_data, [o.name for o in ORG_FEATURES_ORGS]
        )

    def test_dota_lobby(self) -> None:
        self._assert_repopulate_clean(populate_dota_lobby_data, [LOBBY_ORG.name])
