import importlib

from django.test import SimpleTestCase

DROPPED_ALIASES = (
    "DiscordEventState",
    "MessageLogEntry",
    "SyncDiscordState",
    "DotaProfileSchema",
    "OrgProxy",
    "EventSignupData",
    "EventTaskData",
    "EventTemplateData",
    "RepeaterSubscriber",
    "ScheduledEventDue",
    "UserSchema",
    "TournamentTaskData",
    "TournamentParticipant",
    "GameWithoutHeroDraft",
)


class AppSchemaReexportTests(SimpleTestCase):
    def test_back_compat_aliases_dropped(self) -> None:
        schemas = importlib.import_module("user.schemas")
        for name in DROPPED_ALIASES:
            with self.subTest(name=name):
                self.assertFalse(hasattr(schemas, name))

    def test_signup_user_data_resolves_tournament_user_schema(self) -> None:
        events_schemas = importlib.import_module("events.schemas")
        user_schemas = importlib.import_module("user.schemas")
        field = events_schemas.EventSignupSchema.model_fields["user_data"]
        self.assertIn(user_schemas.TournamentUserSchema, field.annotation.__args__)
