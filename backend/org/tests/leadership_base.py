from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from draft.models import Draft, TeamDraftState
from events.completion import close_event
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership.lifecycle import SnapshotResult, snapshot_event
from org.leadership.reviews import submit_review
from org.models import ContributionEntry, Organization, OrgUser
from org.models_leadership import CaptainReview, EventCaptain
from org.tests.conduct_base import ConductTestCase
from tournament.models import Team, Tournament

ALL_FIVES = {"communication": 5, "drafting": 5, "composure": 5, "sportsmanship": 5}


def scores(value: int) -> dict[str, int]:
    return {key: value for key in ALL_FIVES}


class LeadershipTestCase(ConductTestCase):
    def setUp(self) -> None:
        self.admin = self.make_user("ld_admin")
        self.org = Organization.objects.create(name="Leadership Org", owner=self.admin)
        self.org.admins.add(self.admin)
        self.unlock_leadership()
        self.event, self.tournament = self.make_event("Cup")
        self.cap_a = self.make_user("ld_cap_a")
        self.cap_b = self.make_user("ld_cap_b")
        self.mates_a = [self.make_user(f"ld_a{i}") for i in range(3)]
        self.mates_b = [self.make_user(f"ld_b{i}") for i in range(2)]
        self.team_a = self.make_team("Alpha", self.cap_a, self.mates_a, placement=1)
        self.team_b = self.make_team("Bravo", self.cap_b, self.mates_b, placement=2)
        for user in [self.cap_a, self.cap_b, *self.mates_a, *self.mates_b]:
            self.admit(user)

    def unlock_leadership(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=True, actor=None)

    def make_user(self, name: str) -> CustomUser:
        return CustomUser.objects.create_user(username=name, password="x")

    def make_event(self, name: str) -> tuple[Event, Tournament]:
        start = tz.now() - timedelta(hours=4)
        tournament = Tournament.objects.create(name=f"{name} T", date_played=start)
        event = Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=start,
            ends_at=start + timedelta(hours=3),
            state=EventState.IN_PROGRESS,
            created_by=self.admin,
            tournament=tournament,
        )
        return event, tournament

    def make_team(
        self,
        name: str,
        captain: CustomUser | None,
        mates: list[CustomUser],
        *,
        placement: int | None = None,
        tournament: Tournament | None = None,
    ) -> Team:
        team = Team.objects.create(
            tournament=tournament or self.tournament,
            name=name,
            captain=captain,
            placement=placement,
        )
        team.members.set([*([captain] if captain else []), *mates])
        return team

    def admit(self, user: CustomUser, event: Event | None = None) -> OrgUser:
        EventSignup.objects.create(
            event=event or self.event, user=user, status=SignupStatus.APPROVED
        )
        org_user, _ = OrgUser.objects.get_or_create(user=user, organization=self.org)
        return org_user

    def ou(self, user: CustomUser) -> OrgUser:
        return OrgUser.objects.nocache().get(user=user, organization=self.org)

    def complete_draft(self, tournament: Tournament | None = None) -> None:
        Draft.objects.create(
            tournament=tournament or self.tournament, state=TeamDraftState.COMPLETED
        )

    def close(
        self, event: Event | None = None, *, state: str = EventState.COMPLETED
    ) -> None:
        close_event(
            event or self.event,
            new_state=EventState(state),
            source="admin",
            actor=self.admin,
        )

    def run_snapshot(
        self, event: Event | None = None, *, now: datetime | None = None
    ) -> SnapshotResult:
        event = event or self.event
        Event.objects.filter(pk=event.pk).update(state=EventState.COMPLETED)
        event.refresh_from_db()
        with transaction.atomic():
            return snapshot_event(event, now=now or tz.now())

    def snapshot(self, captain: CustomUser, event: Event | None = None) -> EventCaptain:
        return EventCaptain.objects.nocache().get(
            event=event or self.event, captain__user=captain
        )

    def review(
        self,
        rater: CustomUser,
        captain: CustomUser,
        value: int | dict[str, int] = 5,
        *,
        now: datetime | None = None,
        event: Event | None = None,
    ) -> CaptainReview:
        return submit_review(
            self.org,
            event_id=(event or self.event).pk,
            captain_org_user_id=self.ou(captain).pk,
            rater=self.ou(rater),
            scores=scores(value) if isinstance(value, int) else value,
            now=now or tz.now(),
        )

    def points(
        self, captain: CustomUser, kind: str, event: Event | None = None
    ) -> int | None:
        return (
            ContributionEntry.objects.nocache()
            .filter(
                org_user__user=captain,
                kind=kind,
                event=event or self.event,
                track="leadership",
            )
            .values_list("points", flat=True)
            .first()
        )

    def expire_window(self, event: Event | None = None) -> None:
        EventCaptain.objects.filter(event=event or self.event).update(
            window_closes_at=tz.now() - timedelta(minutes=1)
        )

    def client_for(self, user: CustomUser) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    def url(self, suffix: str) -> str:
        return f"/api/organizations/{self.org.pk}/leadership/{suffix}"
