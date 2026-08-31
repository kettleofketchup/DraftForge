"""Shared, game-agnostic Discord components for event signup.

Game-agnostic RSVP buttons, the screenshot-upload infra, the modal-v2 sender,
and the shared friend-id field helper live here. Per-game UI lives in the
sibling modules (``dota.py``, ``deadlock.py``, ``default.py``); the provider
registry is in ``registry.py``.

Business logic lives in events/discord (handle_signup_button, etc.), reached
over HTTP via discordbot.internal_client.signup_actions.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import discord
from asgiref.sync import sync_to_async
from discord import ui
from django.conf import settings

from discordbot.custom_ids import (
    CustomId,
    DeclineId,
    NotifyId,
    ScreenshotFileId,
    ScreenshotUploadId,
    ScreenshotUrlId,
    SignupFriendId,
    SignupId,
    TentativeId,
)
from discordbot.internal_client.signup_actions import (
    decline_button,
    notify_button,
    screenshot_upload,
    signup_button,
    tentative_button,
)
from discordbot.log_context import discord_log_context
from discordbot.signup_responses import respond_to_signup_user
from telemetry.logging import get_logger

log = get_logger(__name__)

SITE_URL = getattr(settings, "SITE_URL", "")
IS_COMPONENTS_V2 = 1 << 15  # 32768


async def send_modal_v2(interaction: discord.Interaction, modal: ui.Modal) -> None:
    """Send a modal with IS_COMPONENTS_V2 flag for Label + Select support.

    discord.py's send_modal doesn't set the V2 flag, so Label-wrapped
    String Selects in modals get rejected. This helper sends the modal
    response manually with the flag included.
    """
    from discord.webhook.async_ import async_context

    adapter = async_context.get()
    http = interaction._state.http

    payload = modal.to_dict()
    payload["flags"] = IS_COMPONENTS_V2

    data = {
        "type": discord.InteractionResponseType.modal.value,
        "data": payload,
    }

    from discord.http import MultipartParameters

    params = MultipartParameters(payload=data, multipart=None, files=None)

    await adapter.create_interaction_response(
        interaction.id,
        interaction.token,
        session=interaction._session,
        proxy=http.proxy,
        proxy_auth=http.proxy_auth,
        params=params,
    )

    if not modal.is_finished():
        interaction._state.store_view(modal)
    interaction.response._response_type = discord.InteractionResponseType.modal


def build_friend_id_input(
    event_id: int, prefill: dict, required: bool
) -> ui.TextInput | None:
    """Shared Steam Friend ID field; returns None when already known or not required."""
    if not required or prefill.get("unverified_friend_id"):
        return None
    return ui.TextInput(
        label="Steam Friend ID",
        placeholder="Your Friend ID (number from your Dotabuff URL)",
        custom_id=SignupFriendId(event_id=event_id).encode(),
        required=True,
        max_length=20,
        style=discord.TextStyle.short,
        default=str(prefill.get("unverified_friend_id", "")),
    )


@runtime_checkable
class GameComponentProvider(Protocol):
    """UI-layer provider protocol (stateless singleton, no ORM).

    Counterpart in the logic layer: ``events.discord.providers`` handlers.
    See ``registry.py`` for the "Adding a game type" checklist.
    """

    bare_select_ids: tuple[type[CustomId], ...]

    def build_signup_modal(
        self, event_id: int, prefill: dict, config: dict
    ) -> ui.Modal: ...

    async def dispatch_bare_select(
        self, interaction: discord.Interaction, cid: CustomId
    ) -> None: ...


class EventSignupView(ui.View):
    """Persistent view attached to event announcement messages.

    Components:
    - Sign Up button (green)
    - Notify Me button (grey, only if event has a repeater)
    - View Event button (link to site)
    """

    def __init__(
        self,
        event_id: int,
        has_repeater: bool = False,
        site_url: str | None = None,
    ) -> None:
        super().__init__(timeout=None)  # Persistent

        # Sign Up button
        self.add_item(SignupButton(event_id))

        # Notify Me — only for repeater events
        if has_repeater:
            self.add_item(NotifyButton(event_id))

        # View Event — link button (no custom_id, opens URL)
        url = site_url or SITE_URL
        if url:
            self.add_item(
                ui.Button(
                    label="View Event",
                    style=discord.ButtonStyle.link,
                    url=f"{url}/events/{event_id}/",
                    emoji="\U0001f517",
                )
            )


class SignupButton(ui.Button):
    """Green 'Sign Up' button. custom_id='event_signup:{event_id}'"""

    def __init__(self, event_id: int) -> None:
        super().__init__(
            label="Sign Up",
            style=discord.ButtonStyle.success,
            custom_id=SignupId(event_id=event_id).encode(),
            emoji="✅",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction,
            custom_id=self.custom_id,
            event_id=self.event_id,
        ) as ctx:
            result = await sync_to_async(signup_button, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                discord_username=interaction.user.name,
            )
            ctx.set_outcome(result["action"])

            if result["action"] == "signed_up":
                await respond_to_signup_user(
                    interaction,
                    content=f"✅ You're signed up! Status: **{result['status']}**",
                )
            elif result["action"] == "needs_modal":
                from discordbot.components.registry import get_component_provider

                provider = get_component_provider(result["game_type"])
                modal = provider.build_signup_modal(
                    self.event_id,
                    result.get("prefill", {}),
                    result.get("modal_config", {}) or {},
                )
                await send_modal_v2(interaction, modal)
            elif result["action"] == "error":
                await interaction.response.send_message(
                    f"❌ {result['message']}",
                    ephemeral=True,
                )


class NotifyButton(ui.Button):
    """Grey 'Notify Me' button. custom_id='event_notify:{event_id}'"""

    def __init__(self, event_id: int) -> None:
        super().__init__(
            label="Notify Me for Future Events",
            style=discord.ButtonStyle.secondary,
            custom_id=NotifyId(event_id=event_id).encode(),
            emoji="\U0001f514",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction, custom_id=self.custom_id, event_id=self.event_id
        ) as ctx:
            result = await sync_to_async(notify_button, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
            )
            ctx.set_outcome("subscribed" if result["subscribed"] else "unsubscribed")

            if result["subscribed"]:
                await interaction.response.send_message(
                    "\U0001f514 You'll be notified about future events in this series!",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "\U0001f515 Notifications turned off for this series.",
                    ephemeral=True,
                )


class TentativeButton(ui.Button):
    """Grey 'Tentative' button. custom_id='event_tentative:{event_id}'"""

    def __init__(self, event_id: int) -> None:
        super().__init__(
            label="Tentative",
            style=discord.ButtonStyle.secondary,
            custom_id=TentativeId(event_id=event_id).encode(),
            emoji="❓",
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction, custom_id=self.custom_id, event_id=self.event_id
        ) as ctx:
            result = await sync_to_async(tentative_button, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                discord_username=interaction.user.name,
            )
            ctx.set_outcome(result["action"])

            if result["action"] == "tentative":
                await respond_to_signup_user(
                    interaction,
                    content="❓ Marked as tentative. We'll count you as interested!",
                )
            elif result["action"] == "error":
                await interaction.response.send_message(
                    result.get("message", "Something went wrong."),
                    ephemeral=True,
                )


class DeclineButton(ui.Button):
    """Grey 'Decline' button. custom_id='event_decline:{event_id}'"""

    def __init__(self, event_id: int) -> None:
        super().__init__(
            label="Decline",
            style=discord.ButtonStyle.secondary,
            custom_id=DeclineId(event_id=event_id).encode(),
        )
        self.event_id = event_id

    async def callback(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction, custom_id=self.custom_id, event_id=self.event_id
        ) as ctx:
            result = await sync_to_async(decline_button, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
            )
            ctx.set_outcome(result["action"])

            if result["action"] == "declined":
                await respond_to_signup_user(
                    interaction, content="You've declined the event."
                )
            elif result["action"] == "not_signed_up":
                await interaction.response.send_message(
                    "You weren't signed up for this event.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    result.get("message", "Something went wrong."), ephemeral=True
                )


# ---------------------------------------------------------------------------
# Screenshot upload flow (V2 modals)
# ---------------------------------------------------------------------------

SCREENSHOT_EXAMPLE_URLS = {
    "rank": "https://assets.kettle.sh/draftforge/discord/rank/dota2/dota2_rank.png",
    "battlecup": "https://assets.kettle.sh/draftforge/discord/rank/dota2/battlecup_ticket.png",
}


class ScreenshotUploadPromptView(ui.View):
    """Ephemeral prompt with Upload Screenshot button."""

    def __init__(self, event_id: int, screenshot_type: str) -> None:
        super().__init__(timeout=300)
        self.event_id = event_id
        self.screenshot_type = screenshot_type
        self.example_url = SCREENSHOT_EXAMPLE_URLS.get(screenshot_type, "")
        self.add_item(ScreenshotUploadButton(event_id, screenshot_type))


class ScreenshotUploadButton(ui.Button):
    """Button that opens the screenshot upload modal."""

    def __init__(self, event_id: int, screenshot_type: str) -> None:
        label = (
            "Upload MMR Screenshot"
            if screenshot_type == "rank"
            else "Upload Battle Cup Screenshot"
        )
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=ScreenshotUploadId(
                event_id=event_id, screenshot_type=screenshot_type
            ).encode(),
            emoji="\U0001f4f8",
        )
        self.event_id = event_id
        self.screenshot_type = screenshot_type

    async def callback(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction, custom_id=self.custom_id, event_id=self.event_id
        ) as ctx:
            if interaction.response.is_done():
                log.warning(
                    "screenshot_upload_already_acknowledged",
                    system="discord",
                    subsystem="interaction",
                )
                ctx.set_outcome("already_acknowledged")
                return
            modal = ScreenshotUploadModal(self.event_id, self.screenshot_type)
            ctx.set_outcome("modal_sent")
            ctx.add(screenshot_type=self.screenshot_type)
            await send_modal_v2(interaction, modal)


class ScreenshotUploadModal(ui.Modal):
    """V2 modal with TextDisplay (example + tips) and FileUpload or URL fallback."""

    def __init__(self, event_id: int, screenshot_type: str) -> None:
        self.event_id = event_id
        self.screenshot_type = screenshot_type

        title = (
            "Upload MMR Screenshot"
            if screenshot_type == "rank"
            else "Upload Battle Cup Screenshot"
        )
        super().__init__(title=title)

        from discordbot.screenshot_tips import SCREENSHOT_TIPS

        example_url = SCREENSHOT_EXAMPLE_URLS.get(screenshot_type, "")

        # Show example + tips (only TextDisplay type 10 is allowed in modals, not MediaGallery)
        if hasattr(ui, "TextDisplay"):
            label = "MMR" if screenshot_type == "rank" else "Battle Cup ticket"
            self.add_item(
                ui.TextDisplay(
                    content=f"**Example {label} screenshot:**\n{example_url}\n\n{SCREENSHOT_TIPS}"
                )
            )

        # Add FileUpload if available, otherwise fall back to TextInput for URL
        if hasattr(ui, "FileUpload"):
            self.file_upload = ui.FileUpload(
                custom_id=ScreenshotFileId(
                    event_id=event_id, screenshot_type=screenshot_type
                ).encode(),
            )
            self.add_item(ui.Label(text="Screenshot", component=self.file_upload))
            self.url_input = None
        else:
            self.file_upload = None
            self.url_input = ui.TextInput(
                label="Catbox Link",
                placeholder="https://files.catbox.moe/abc123.png",
                custom_id=ScreenshotUrlId(
                    event_id=event_id, screenshot_type=screenshot_type
                ).encode(),
                required=True,
                style=discord.TextStyle.short,
            )
            self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        async with discord_log_context(
            interaction,
            custom_id=ScreenshotUploadId(
                event_id=self.event_id, screenshot_type=self.screenshot_type
            ).encode(),
            event_id=self.event_id,
            tags=["events", "signup"],
        ) as ctx:
            if self.file_upload and interaction.data.get("resolved", {}).get("files"):
                files = interaction.data["resolved"]["files"]
                attachment_url = list(files.values())[0].get("url", "") if files else ""
            elif self.url_input:
                attachment_url = self.url_input.value
            else:
                attachment_url = ""

            result = await sync_to_async(screenshot_upload, thread_sensitive=False)(
                event_id=self.event_id,
                discord_user_id=str(interaction.user.id),
                screenshot_type=self.screenshot_type,
                attachment_url=attachment_url,
            )
            ctx.set_outcome(
                "signed_up"
                if result.get("signed_up")
                else "screenshot_saved"
                if result.get("success")
                else "error"
            )
            ctx.add(screenshot_type=self.screenshot_type)

            if result.get("success"):
                if result.get("signed_up"):
                    await respond_to_signup_user(
                        interaction,
                        content=f"✅ {result.get('message', 'Screenshot uploaded! You are signed up.')}",
                    )
                else:
                    await respond_to_signup_user(
                        interaction,
                        content=f"✅ {result.get('message', 'Screenshot saved.')}",
                    )
            else:
                await interaction.response.send_message(
                    f"❌ {result.get('message', 'Upload failed.')}",
                    ephemeral=True,
                )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        async with discord_log_context(
            interaction,
            custom_id=ScreenshotUploadId(
                event_id=self.event_id, screenshot_type=self.screenshot_type
            ).encode(),
            event_id=self.event_id,
            tags=["events", "signup"],
        ):
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Something went wrong.",
                        ephemeral=True,
                    )
                else:
                    await interaction.followup.send(
                        "❌ Something went wrong.",
                        ephemeral=True,
                    )
            finally:
                raise error
