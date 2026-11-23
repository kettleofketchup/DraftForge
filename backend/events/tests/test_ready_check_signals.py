import ast
from pathlib import Path
from typing import Any
from unittest import mock

from django.dispatch import Signal

from events import ready_check_signals
from events.constants import SignupAction
from events.ledger import SignupActor, record_ready_check_transition
from events.models import ReadyCheck
from events.ready_check_signals import ReadyCheckChange, send_on_commit
from events.tests.base import EventTestCase


class ReadyCheckTransitionRowTest(EventTestCase):
    def test_record_transition_writes_event_level_row(self) -> None:
        check = ReadyCheck.objects.create(event=self.event)
        entry = record_ready_check_transition(
            event=self.event,
            actor=SignupActor.system(),
            check=check,
            step="open",
            extra={"asked": 3},
        )
        entry.refresh_from_db()
        self.assertIsNone(entry.signup)
        self.assertIsNone(entry.subject_user)
        self.assertEqual(entry.subject_snapshot, {})
        self.assertFalse(entry.on_behalf)
        self.assertEqual(entry.action, SignupAction.READY_CHECK_TRANSITION)
        self.assertEqual(entry.action, "ready_check_transition")
        self.assertEqual(entry.correlation_id, f"rc{check.pk}:open")
        self.assertEqual(entry.reason, "open")
        self.assertEqual(entry.after["extra"]["asked"], 3)
        self.assertEqual(entry.after["extra"]["step"], "open")
        self.assertEqual(entry.after["extra"]["phase"], check.phase)
        self.assertEqual(entry.after["extra"]["outcome"], check.outcome)
        self.assertEqual(entry.organization_id, self.event.organization_id)


class ReadyCheckSignalsTest(EventTestCase):
    def setUp(self) -> None:
        self.signal = Signal()
        self.change = ReadyCheckChange(
            event_id=self.event.pk,
            ready_check_id=1,
            phase="open",
            outcome="",
            user_ids=(self.user.pk,),
        )

    def test_send_on_commit_defers_until_commit(self) -> None:
        receiver = mock.Mock(return_value=None)
        self.signal.connect(receiver, weak=False)
        self.addCleanup(self.signal.disconnect, receiver)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            send_on_commit(self.signal, self.change)
        receiver.assert_not_called()
        for callback in callbacks:
            callback()
        receiver.assert_called_once()
        self.assertIs(receiver.call_args.kwargs["change"], self.change)
        self.assertIs(receiver.call_args.kwargs["sender"], ReadyCheckChange)

    def test_receiver_failure_is_logged_not_raised(self) -> None:
        def boom(**_: Any) -> None:
            raise RuntimeError("boom")

        self.signal.connect(boom, weak=False)
        self.addCleanup(self.signal.disconnect, boom)
        with mock.patch.object(ready_check_signals, "log") as log:
            with self.captureOnCommitCallbacks(execute=True):
                send_on_commit(self.signal, self.change)
        log.warning.assert_called_once()
        self.assertEqual(
            log.warning.call_args.args[0], "ready_check_signal_receiver_failed"
        )

    def test_signals_module_imports_no_models(self) -> None:
        path = Path(ready_check_signals.__file__)
        tree = ast.parse(path.read_text())
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "models" or node.module.endswith(".models"):
                    offenders.append(node.module)
                if any(alias.name == "models" for alias in node.names):
                    offenders.append(f"{node.module}.models")
            elif isinstance(node, ast.Import):
                offenders.extend(
                    alias.name for alias in node.names if alias.name.endswith(".models")
                )
        self.assertEqual(offenders, [])
