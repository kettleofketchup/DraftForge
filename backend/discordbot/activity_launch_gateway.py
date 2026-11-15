"""Gateway-safe launch handlers: never import ORM-backed Activity modules."""

from typing import Any

import discord
from asgiref.sync import sync_to_async

from app.internal_client import _post


def prepare_launch_payload(
    discord_user_id: str, kind: str, draft_id: int
) -> dict[str, Any]:
    response = _post(
        "/discord/activity-launch/",
        {
            "discord_user_id": str(discord_user_id),
            "kind": kind,
            "draft_id": draft_id,
        },
    )
    if response is not None and response.ok:
        try:
            payload = response.json()
            if isinstance(payload.get("content"), str) and isinstance(
                payload.get("components"), list
            ):
                return payload
        except (ValueError, TypeError, AttributeError):
            pass
    return {
        "success": False,
        "content": "Could not prepare the Activity. Please try again shortly.",
        "components": [],
    }


def launch_view(components: list[dict[str, Any]]) -> discord.ui.View | None:
    if not components:
        return None
    view = discord.ui.View(timeout=None)
    for row in components:
        for item in row.get("components", []):
            if item.get("type") == 2 and item.get("style") == 5:
                view.add_item(discord.ui.Button(label=item["label"], url=item["url"]))
    return view


async def handle_draft_launch(
    interaction: discord.Interaction, kind: str, draft_id: int
) -> None:
    await interaction.response.defer(ephemeral=True, thinking=True)
    payload = await sync_to_async(prepare_launch_payload, thread_sensitive=False)(
        str(interaction.user.id), kind, draft_id
    )
    await interaction.edit_original_response(
        content=payload["content"], view=launch_view(payload["components"])
    )
