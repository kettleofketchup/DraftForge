import threading
import time
from datetime import timedelta
from unittest import mock

from django.db import OperationalError, close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone as tz

from app.models import CustomUser, Organization
from events import line
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from events.services import create_tentative_signup, decline_signup, process_rsvp


class SignupLineSeqTransactionTests(TransactionTestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Race Line Org")
        self.users = [
            CustomUser.objects.create_user(username=f"race_line_{i}", password="x")
            for i in range(4)
        ]
        self.event = Event.objects.create(
            organization=self.org,
            name="Race Line Event",
            scheduled_at=tz.now() + timedelta(days=1),
            state=EventState.SIGNUPS_OPEN,
            max_players=1,
        )

    def test_stamp_inside_atomic_at_every_create_site(self) -> None:
        records: list[tuple[str, bool]] = []
        real = line.next_line_seq
        site = ""

        def wrapper(event: Event) -> int:
            records.append((site, connection.in_atomic_block))
            return real(event)

        self.assertFalse(connection.in_atomic_block)
        with mock.patch("events.line.next_line_seq", side_effect=wrapper):
            site = "process_rsvp_seated"
            seated = process_rsvp(self.event, self.users[0])
            site = "process_rsvp_waitlisted"
            waitlisted = process_rsvp(self.event, self.users[1])
            site = "create_tentative_signup"
            create_tentative_signup(self.event, self.users[2])
            site = "decline_signup"
            decline_signup(self.event, self.users[3])

        self.assertEqual(seated.status, SignupStatus.RSVP)
        self.assertEqual(waitlisted.status, SignupStatus.WAITLISTED)
        self.assertEqual(
            [name for name, _ in records],
            [
                "process_rsvp_seated",
                "process_rsvp_waitlisted",
                "create_tentative_signup",
                "decline_signup",
            ],
        )
        self.assertTrue(all(in_atomic for _, in_atomic in records), records)

    def test_concurrent_rsvp_seqs(self) -> None:
        """Smoke only: retries serialize the writers; the atomic test is the proof."""
        self.event.max_players = 10
        self.event.save()
        barrier = threading.Barrier(2)
        seqs: list[int] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker(user: CustomUser) -> None:
            try:
                barrier.wait(timeout=5)
                for attempt in range(1, 21):
                    try:
                        signup: EventSignup = process_rsvp(self.event, user)
                        break
                    except OperationalError:
                        time.sleep(0.05 * attempt)
                else:
                    raise RuntimeError("process_rsvp kept failing")
                with lock:
                    seqs.append(signup.line_seq)
            except BaseException as exc:
                with lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(u,)) for u in self.users[:2]]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(seqs), [1, 2])
        self.assertEqual(
            sorted(
                EventSignup.objects.filter(event=self.event).values_list(
                    "line_seq", flat=True
                )
            ),
            [1, 2],
        )
