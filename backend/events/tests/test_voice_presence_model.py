from events.constants import (
    ActorRole,
    SignupAction,
    SignupMeans,
    VoicePresenceSource,
)
from events.ledger import SignupActor, record_signup_change
from events.models import EventSignup, EventVoicePresence
from events.tests.base import EventTestCase


class VoicePresenceModelTest(EventTestCase):
    def test_source_defaults_to_feed(self) -> None:
        row = EventVoicePresence.objects.create(event=self.event, user=self.user)

        row.refresh_from_db()
        self.assertEqual(row.source, VoicePresenceSource.FEED)

    def test_voice_actor(self) -> None:
        actor = SignupActor.voice(self.user)

        self.assertEqual(actor.role, ActorRole.MEMBER)
        self.assertEqual(actor.means, SignupMeans.DISCORD_VOICE)
        self.assertEqual(actor.user, self.user)
        self.assertEqual(actor.correlation_id, "")

    def test_voice_actor_correlation_id(self) -> None:
        actor = SignupActor.voice(self.user, correlation_id="rc1:2")

        self.assertEqual(actor.correlation_id, "rc1:2")

    def test_ledger_accepts_voice_values(self) -> None:
        signup = EventSignup.objects.create(event=self.event, user=self.user)

        entry = record_signup_change(
            event=self.event,
            subject=self.user,
            actor=SignupActor.voice(self.user),
            action=SignupAction.VOICE_PRESENCE_SET,
            signup=signup,
        )

        # Not blank=True, so empty on a minimal entry and never valid here.
        entry.clean_fields(exclude=["before", "after", "rules_overridden", "caused_by"])
        self.assertEqual(entry.means, SignupMeans.DISCORD_VOICE)
        self.assertEqual(entry.action, SignupAction.VOICE_PRESENCE_SET)
