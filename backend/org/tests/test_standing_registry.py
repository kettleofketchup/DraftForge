import inspect

from django.test import SimpleTestCase

from org.standing import registry
from org.standing.base import TrackBase
from org.standing.kinds import CONTRIBUTION_KINDS, LedgerKind, build_kinds
from org.standing.types import Metric, OutputKeys
from org.tests.standing_fakes import FAKE_POINTS, FakeTrack


class AdapterConformanceTest(SimpleTestCase):
    def test_overrides_match_base_signatures(self) -> None:
        for track in (*registry.TRACKS, FakeTrack()):
            for name, member in inspect.getmembers(type(track), inspect.isfunction):
                if name.startswith("_"):
                    continue
                with self.subTest(track=track.key, method=name):
                    self.assertTrue(
                        hasattr(TrackBase, name), f"{name} is not a TrackBase hook"
                    )
                    base = inspect.signature(getattr(TrackBase, name))
                    mine = inspect.signature(member)
                    self.assertEqual(
                        [(p.name, p.kind, p.default) for p in mine.parameters.values()],
                        [(p.name, p.kind, p.default) for p in base.parameters.values()],
                    )

    def test_registry_is_valid(self) -> None:
        registry.validate_tracks(registry.TRACKS)
        self.assertEqual(
            [t.key for t in registry.tracks()],
            ["contribution", "conduct", "leadership"],
        )


class KindsTest(SimpleTestCase):
    def test_duplicate_kind_rejected(self) -> None:
        extra = (
            (
                "manual",
                LedgerKind(track="leadership", default_points=1, once_per_event=False),
            ),
        )
        with self.assertRaises(ValueError):
            build_kinds(CONTRIBUTION_KINDS, extra)


class ValidateTracksTest(SimpleTestCase):
    def test_duplicate_track_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            registry.validate_tracks([FakeTrack(), FakeTrack()])

    def test_default_metric_must_be_unique(self) -> None:
        other = Metric(key="other", label="Other", format="int", periodic=True)
        for metrics in ((other,), (FAKE_POINTS, FAKE_POINTS)):
            fake = FakeTrack()
            fake.metrics = metrics  # type: ignore[misc]
            with self.subTest(metrics=metrics), self.assertRaises(ValueError):
                registry.validate_tracks([fake])

    def test_output_key_collision_rejected(self) -> None:
        a, b = FakeTrack("a"), FakeTrack("b")
        a.output_keys = {"on_event_closed": OutputKeys(orglog=("awarded",))}  # type: ignore[misc]
        b.output_keys = {"on_event_closed": OutputKeys(orglog=("awarded",))}  # type: ignore[misc]
        with self.assertRaises(ValueError):
            registry.validate_tracks([a, b])

    def test_merge_namespace_collision_rejected(self) -> None:
        a, b = FakeTrack("a"), FakeTrack("b")
        a.output_keys = {"merge_members": OutputKeys(orglog=("x",))}  # type: ignore[misc]
        b.output_keys = {"repoint_user": OutputKeys(orglog=("x",))}  # type: ignore[misc]
        with self.assertRaises(ValueError):
            registry.validate_tracks([a, b])

    def test_merge_key_reused_within_track_rejected(self) -> None:
        a = FakeTrack("a")
        a.output_keys = {  # type: ignore[misc]
            "merge_members": OutputKeys(orglog=("x",)),
            "repoint_user": OutputKeys(orglog=("x",)),
        }
        with self.assertRaises(ValueError):
            registry.validate_tracks([a])

    def test_two_fakes_with_distinct_keys_validate(self) -> None:
        registry.validate_tracks([FakeTrack("fake"), FakeTrack("fake2")])

    def test_override_tracks_restores(self) -> None:
        before = registry.tracks()
        fake = FakeTrack()
        with registry.override_tracks(fake):
            self.assertEqual(registry.tracks(), (fake,))
        self.assertEqual(registry.tracks(), before)
