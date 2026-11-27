"""Typed Discord message payloads (embeds, components, Components V2).

Layered rather than recursive, because zod-from-json-schema.mjs rejects
recursive $defs. Django-free so exporters can run under ``python -I``.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class EmbedField(_Model):
    name: str
    value: str
    inline: bool | None = None


class EmbedAuthor(_Model):
    name: str
    url: str | None = None
    icon_url: str | None = None


class EmbedFooter(_Model):
    text: str
    icon_url: str | None = None


class EmbedMedia(_Model):
    url: str


class Embed(_Model):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    timestamp: str | None = None
    author: EmbedAuthor | None = None
    footer: EmbedFooter | None = None
    thumbnail: EmbedMedia | None = None
    image: EmbedMedia | None = None
    fields: list[EmbedField] = []


class Emoji(_Model):
    id: str | None = None
    name: str | None = None
    animated: bool | None = None


class Button(_Model):
    type: Literal[2]
    style: Literal[1, 2, 3, 4, 5, 6]
    label: str | None = None
    emoji: Emoji | None = None
    url: str | None = None
    custom_id: str | None = None
    disabled: bool | None = None


class SelectOption(_Model):
    label: str
    value: str
    description: str | None = None
    emoji: Emoji | None = None
    default: bool | None = None


class SelectMenu(_Model):
    type: Literal[3, 5, 6, 7, 8]
    custom_id: str
    placeholder: str | None = None
    options: list[SelectOption] = []
    min_values: int | None = None
    max_values: int | None = None
    disabled: bool | None = None


class ActionRow(_Model):
    type: Literal[1]
    components: list[Annotated[Button | SelectMenu, Field(discriminator="type")]] = []


class TextDisplay(_Model):
    type: Literal[10]
    content: str


class UnfurledMedia(_Model):
    url: str


class Thumbnail(_Model):
    type: Literal[11]
    media: UnfurledMedia
    description: str | None = None
    spoiler: bool | None = None


class Section(_Model):
    type: Literal[9]
    components: list[TextDisplay] = []
    accessory: Annotated[Thumbnail | Button, Field(discriminator="type")]


class MediaGalleryItem(_Model):
    media: UnfurledMedia
    description: str | None = None
    spoiler: bool | None = None


class MediaGallery(_Model):
    type: Literal[12]
    items: list[MediaGalleryItem] = []


class Separator(_Model):
    type: Literal[14]
    divider: bool | None = None
    spacing: int | None = None


ContainerChild = Annotated[
    ActionRow | Section | TextDisplay | Separator | MediaGallery,
    Field(discriminator="type"),
]


class Container(_Model):
    type: Literal[17]
    accent_color: int | None = None
    spoiler: bool | None = None
    components: list[ContainerChild] = []


TopLevelComponent = Annotated[
    ActionRow | Container | Section | TextDisplay | Separator | MediaGallery,
    Field(discriminator="type"),
]


class DiscordMessage(_Model):
    content: str | None = None
    embeds: list[Embed] = []
    components: list[TopLevelComponent] = []
    allowed_mentions: dict[str, Any] | None = None
    flags: int | None = None
