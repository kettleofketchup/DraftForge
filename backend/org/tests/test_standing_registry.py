import inspect

from django.test import SimpleTestCase

from org.standing import registry
from org.standing.base import TrackBase
from org.standing.kinds import CONTRIBUTION_KINDS, LedgerKind, build_kinds


class AdapterConformanceTest(SimpleTestCase):
    def test_overrides_match_base_signatures(self) -> None:
        for track in registry.TRACKS:
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
        registry.validate(registry.TRACKS)
        self.assertEqual([t.key for t in registry.tracks()], ["contribution"])


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
