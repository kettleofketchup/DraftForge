import type {
  DiscordPreviewRequest,
  DiscordPreviewResponse,
} from './schemas.generated';

export {
  ActionRowSchema,
  ButtonSchema,
  ContainerSchema,
  DiscordMessageSchema,
  DiscordPreviewRequestSchema,
  DiscordPreviewResponseSchema,
  EmbedSchema,
  GateSchema,
  MediaGallerySchema,
  MentionsSchema,
  PreviewDestinationSchema,
  ScheduledEventPreviewSchema,
  SectionSchema,
  SelectMenuSchema,
  SeparatorSchema,
  TextDisplaySchema,
  ThumbnailSchema,
  VariantSchema,
  type ActionRow,
  type Button,
  type Container,
  type DiscordMessage,
  type DiscordPreviewRequest,
  type DiscordPreviewResponse,
  type Embed,
  type EmbedAuthor,
  type EmbedField,
  type EmbedFooter,
  type EmbedMedia,
  type Emoji,
  type EventContext,
  type Gate,
  type MediaGallery,
  type MediaGalleryItem,
  type Mentions,
  type NewEventContext,
  type NewRepeaterContext,
  type OrgDefaultsContext,
  type PreviewDestination,
  type RepeaterContext,
  type ScheduledEventPreview,
  type Section,
  type SelectMenu,
  type SelectOption,
  type Separator,
  type SeriesOneOffContext,
  type TextDisplay,
  type Thumbnail,
  type UnfurledMedia,
  type Variant,
} from './schemas.generated';

export type PreviewKind = DiscordPreviewResponse['kind'];
export type PreviewStatus = DiscordPreviewResponse['status'];
export type PreviewContext = DiscordPreviewRequest['context'];
export type PreviewContextType = PreviewContext['type'];
export type GateCode = DiscordPreviewResponse['gate']['reasons'][number];
export type NoteCode = DiscordPreviewResponse['notes'][number];
export type PreviewDestinationType = NonNullable<
  DiscordPreviewResponse['destination']
>['type'];
