"""team_roster_changed fires on commit with the Team class as sender."""

from typing import Any

from django.test import TestCase
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser, Team, TeamLog, TeamLogAction, TeamLogVia, Tournament
from app.services.team_signals import (
    TeamRosterChange,
    change_from_log,
    owning_team_audit,
    send_roster_changed_on_commit,
    team_audit_owner,
    team_roster_changed,
)
from app.signals import team_roster_changed as reexported_signal


class TeamRosterSignalTests(TestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="Signal Cup", date_played=timezone.now()
        )
        self.team = Team.objects.create(tournament=self.tournament, name="Signals")
        self.actor = CustomUser.objects.create_user(username="sig_actor", password="x")
        self.target = CustomUser.objects.create_user(
            username="sig_target", password="x"
        )
        self.log = TeamLog.objects.create(
            team=self.team,
            team_snapshot_id=self.team.pk,
            tournament_id=self.tournament.pk,
            event_id=None,
            team_name=self.team.name,
            actor=self.actor,
            target_user=self.target,
            via=TeamLogVia.WEB,
            action=TeamLogAction.SUB_IN,
            reason="late",
            override_rules=["team_standin_cap"],
            details={
                "before": {"member_ids": [1]},
                "after": {"member_ids": [1, 2]},
                "replacing_user_id": 7,
            },
        )
        self.calls: list[dict[str, Any]] = []

    def connect(self, receiver: Any) -> None:
        team_roster_changed.connect(receiver, sender=Team, weak=False)
        self.addCleanup(team_roster_changed.disconnect, receiver, sender=Team)

    def record(self, sender: Any, change: TeamRosterChange, **kwargs: Any) -> None:
        self.calls.append({"sender": sender, "change": change})

    def test_reexported_from_app_signals(self) -> None:
        self.assertIs(reexported_signal, team_roster_changed)

    def test_change_from_log(self) -> None:
        change = change_from_log(self.log)

        self.assertEqual(change.log_id, self.log.pk)
        self.assertEqual(change.team_id, self.team.pk)
        self.assertEqual(change.tournament_id, self.tournament.pk)
        self.assertIsNone(change.event_id)
        self.assertEqual(change.action, "sub_in")
        self.assertEqual(change.via, "web")
        self.assertEqual(change.actor_id, self.actor.pk)
        self.assertEqual(change.target_user_id, self.target.pk)
        self.assertEqual(change.replacing_user_id, 7)
        self.assertEqual(change.reason, "late")
        self.assertEqual(change.override_codes, ["team_standin_cap"])
        self.assertEqual(change.before, {"member_ids": [1]})
        self.assertEqual(change.after, {"member_ids": [1, 2]})

    def test_change_from_log_minimal_details(self) -> None:
        self.log.details = {}
        self.log.save()

        change = change_from_log(self.log)

        self.assertIsNone(change.replacing_user_id)
        self.assertEqual(change.before, {})
        self.assertEqual(change.after, {})

    def test_not_sent_before_commit(self) -> None:
        self.connect(self.record)

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            send_roster_changed_on_commit(change_from_log(self.log))

        self.assertEqual(self.calls, [])
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["change"].log_id, self.log.pk)

    def test_sender_is_team_class(self) -> None:
        self.connect(self.record)

        with self.captureOnCommitCallbacks(execute=True):
            send_roster_changed_on_commit(change_from_log(self.log))

        self.assertEqual(len(self.calls), 1)
        self.assertIs(self.calls[0]["sender"], Team)

    def test_raising_receiver_logged(self) -> None:
        def boom(sender: Any, change: TeamRosterChange, **kwargs: Any) -> None:
            raise RuntimeError("listener broke")

        self.connect(boom)
        self.connect(self.record)

        with capture_logs() as logs:
            with self.captureOnCommitCallbacks(execute=True):
                send_roster_changed_on_commit(change_from_log(self.log))

        failures = [e for e in logs if e["event"] == "team_roster_listener_failed"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["log_level"], "error")
        self.assertEqual(failures[0]["system"], "tournament")
        self.assertEqual(failures[0]["subsystem"], "teams")
        self.assertEqual(failures[0]["log_id"], self.log.pk)
        self.assertIn("boom", failures[0]["receiver"])
        self.assertEqual(len(self.calls), 1)

    def test_owning_team_audit_resets(self) -> None:
        self.assertFalse(team_audit_owner.get())
        with owning_team_audit():
            self.assertTrue(team_audit_owner.get())
        self.assertFalse(team_audit_owner.get())

        with self.assertRaises(ValueError):
            with owning_team_audit():
                self.assertTrue(team_audit_owner.get())
                raise ValueError("inside")
        self.assertFalse(team_audit_owner.get())

    def test_owning_team_audit_nested(self) -> None:
        with owning_team_audit():
            with owning_team_audit():
                self.assertTrue(team_audit_owner.get())
            self.assertTrue(team_audit_owner.get())
        self.assertFalse(team_audit_owner.get())
