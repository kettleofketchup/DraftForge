"""Bind local/test voice channels and print a Components V2 launch payload."""

import json
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from app.models import Draft, HeroDraft
from discordbot.activity import launch_message
from discordbot.models import DraftActivityChannel


class Command(BaseCommand):
    help = "Bind a Discord voice channel to an existing hero or team draft (does not send messages)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("guild_id")
        parser.add_argument("channel_id")
        parser.add_argument("kind", choices=["hero", "team"])
        parser.add_argument("draft_id", type=int)

    def handle(self, *args: Any, **options: Any) -> None:
        for key in ("guild_id", "channel_id"):
            if not options[key].isdigit() or len(options[key]) > 20:
                raise CommandError(f"{key} must be a Discord snowflake.")
        model = HeroDraft if options["kind"] == "hero" else Draft
        if not model.objects.filter(pk=options["draft_id"]).exists():
            raise CommandError("Draft does not exist.")
        DraftActivityChannel.objects.update_or_create(
            channel_id=options["channel_id"],
            defaults={
                "guild_id": options["guild_id"],
                "draft_id": options["draft_id"] if options["kind"] == "hero" else None,
                "team_draft_id": options["draft_id"]
                if options["kind"] == "team"
                else None,
            },
        )
        self.stdout.write(json.dumps(launch_message(), indent=2))
