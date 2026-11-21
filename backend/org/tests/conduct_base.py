from datetime import datetime

from django.utils import timezone as tz

from app.models import CustomUser
from events.models import Event, EventSignup
from events.tests.base import EventTestCase
from org.conduct.constants import Outcome, OutcomeSource
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome


class ConductTestCase(EventTestCase):
    def unlock(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=True, actor=None)

    def org_user(self, user: CustomUser) -> OrgUser:
        org_user, _ = OrgUser.objects.get_or_create(user=user, organization=self.org)
        return org_user

    def outcome(
        self,
        user: CustomUser,
        *,
        event: Event | None = None,
        outcome: str = Outcome.ATTENDED,
        source: str = OutcomeSource.DEFAULT,
        finalized: bool = True,
        starts_at: datetime | None = None,
        **kw: object,
    ) -> AttendanceOutcome:
        now = tz.now()
        fields: dict[str, object] = {
            "organization": self.org,
            "org_user": self.org_user(user),
            "event": event,
            "event_name": event.name if event is not None else "Past Event",
            "event_starts_at": starts_at
            or (event.scheduled_at if event is not None else now),
            "outcome": outcome,
            "source": source,
            "finalized_at": now if finalized else None,
        }
        fields.update(kw)
        return AttendanceOutcome.objects.create(**fields)

    def signup(self, event: Event, user: CustomUser, status: str) -> EventSignup:
        return EventSignup.objects.create(event=event, user=user, status=status)
