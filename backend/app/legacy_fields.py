from typing import Any

from rest_framework import serializers


class LegacyNullField(serializers.Field):
    """Keeps a retired key on the wire as null for clients that still require it."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["read_only"] = True
        kwargs.pop("source", None)
        super().__init__(**kwargs)

    def get_attribute(self, instance: Any) -> None:
        return None

    def to_representation(self, value: Any) -> None:
        return None
