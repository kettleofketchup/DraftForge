"""Plain unittest: `python -m unittest common.tests.test_zod_export` from backend/."""

import io
import json
from unittest import TestCase

from pydantic import BaseModel, ConfigDict

from common.zod_export import BUNDLE_VERSION, write_bundle, zod_bundle


class Item(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    name: str
    count: int = 0


class Root(BaseModel):
    items: tuple[Item, ...]


class Other(BaseModel):
    x: int


ROOT = Root(items=(Item(name="a"),))


class ZodBundleTest(TestCase):
    def test_schema_only(self) -> None:
        b = zod_bundle(Root, source="s.py", regen="just r")
        self.assertEqual(b["version"], BUNDLE_VERSION)
        self.assertEqual((b["source"], b["regen"]), ("s.py", "just r"))
        self.assertEqual(b["schema"], Root.model_json_schema(mode="serialization"))
        self.assertNotIn("data", b)

    def test_with_data(self) -> None:
        b = zod_bundle(Root, source="s", regen="r", data=ROOT, data_name="ROOT")
        self.assertEqual(
            b["data"],
            {
                "name": "ROOT",
                "type": "Root",
                "value": {"items": [{"name": "a", "count": 0}]},
            },
        )

    def test_defaults_required_when_configured(self) -> None:
        item = zod_bundle(Root, source="s", regen="r")["schema"]["$defs"]["Item"]
        self.assertEqual(set(item["required"]), {"name", "count"})

    def test_data_and_name_go_together(self) -> None:
        with self.assertRaisesRegex(ValueError, "go together"):
            zod_bundle(Root, source="s", regen="r", data=ROOT)
        with self.assertRaisesRegex(ValueError, "go together"):
            zod_bundle(Root, source="s", regen="r", data_name="ROOT")

    def test_data_must_match_model(self) -> None:
        with self.assertRaisesRegex(TypeError, "Root"):
            zod_bundle(Root, source="s", regen="r", data=Other(x=1), data_name="X")

    def test_write_bundle(self) -> None:
        b = zod_bundle(Root, source="s", regen="r", data=ROOT, data_name="ROOT")
        out = io.StringIO()
        write_bundle(b, out)
        self.assertTrue(out.getvalue().endswith("}\n"))
        self.assertEqual(json.loads(out.getvalue()), b)
