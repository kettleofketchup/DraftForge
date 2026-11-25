import type {
  ActionRow,
  Container,
  DiscordMessage,
  Section,
} from '~/features/event-discord-preview/schemas.generated';

export {
  ActionRowSchema,
  ButtonSchema,
  ContainerSchema,
  DiscordMessageSchema,
  EmbedSchema,
  MediaGallerySchema,
  MentionsSchema,
  SectionSchema,
  SelectMenuSchema,
  SeparatorSchema,
  TextDisplaySchema,
  ThumbnailSchema,
  type ActionRow,
  type Button,
  type Container,
  type DiscordMessage,
  type Embed,
  type EmbedAuthor,
  type EmbedField,
  type EmbedFooter,
  type EmbedMedia,
  type Emoji,
  type MediaGallery,
  type MediaGalleryItem,
  type Mentions,
  type Section,
  type SelectMenu,
  type SelectOption,
  type Separator,
  type TextDisplay,
  type Thumbnail,
  type UnfurledMedia,
} from '~/features/event-discord-preview/schemas.generated';

export type TopLevelComponent = DiscordMessage['components'][number];
export type ContainerChild = Container['components'][number];
export type ActionRowChild = ActionRow['components'][number];
export type SectionAccessory = Section['accessory'];

export type DiscordResolver = {
  users?: Record<string, string>;
  roles?: Record<string, { name: string; color?: number }>;
  channels?: Record<string, string>;
};
