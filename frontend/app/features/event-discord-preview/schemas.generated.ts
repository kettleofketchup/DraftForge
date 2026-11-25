// GENERATED FILE - DO NOT EDIT.
// Source: backend/events/discord/preview_schema.py
// Regenerate with: just py::gen-discord-preview
import { z } from 'zod';

export const EmbedAuthorSchema = z.object({
  name: z.string(),
  url: z.union([z.string(), z.null()]),
  icon_url: z.union([z.string(), z.null()]),
});
export type EmbedAuthor = z.infer<typeof EmbedAuthorSchema>;

export const EmbedFieldSchema = z.object({
  name: z.string(),
  value: z.string(),
  inline: z.union([z.boolean(), z.null()]),
});
export type EmbedField = z.infer<typeof EmbedFieldSchema>;

export const EmbedFooterSchema = z.object({
  text: z.string(),
  icon_url: z.union([z.string(), z.null()]),
});
export type EmbedFooter = z.infer<typeof EmbedFooterSchema>;

export const EmbedMediaSchema = z.object({ url: z.string() });
export type EmbedMedia = z.infer<typeof EmbedMediaSchema>;

export const EmbedSchema = z.object({
  title: z.union([z.string(), z.null()]),
  description: z.union([z.string(), z.null()]),
  url: z.union([z.string(), z.null()]),
  color: z.union([z.number().int(), z.null()]),
  timestamp: z.union([z.string(), z.null()]),
  author: z.union([EmbedAuthorSchema, z.null()]),
  footer: z.union([EmbedFooterSchema, z.null()]),
  thumbnail: z.union([EmbedMediaSchema, z.null()]),
  image: z.union([EmbedMediaSchema, z.null()]),
  fields: z.array(EmbedFieldSchema),
});
export type Embed = z.infer<typeof EmbedSchema>;

export const EmojiSchema = z.object({
  id: z.union([z.string(), z.null()]),
  name: z.union([z.string(), z.null()]),
  animated: z.union([z.boolean(), z.null()]),
});
export type Emoji = z.infer<typeof EmojiSchema>;

export const ButtonSchema = z.object({
  type: z.literal(2),
  style: z.union([
    z.literal(1),
    z.literal(2),
    z.literal(3),
    z.literal(4),
    z.literal(5),
    z.literal(6),
  ]),
  label: z.union([z.string(), z.null()]),
  emoji: z.union([EmojiSchema, z.null()]),
  url: z.union([z.string(), z.null()]),
  custom_id: z.union([z.string(), z.null()]),
  disabled: z.union([z.boolean(), z.null()]),
});
export type Button = z.infer<typeof ButtonSchema>;

export const EventContextSchema = z
  .object({ type: z.literal('event'), event_id: z.number().int() })
  .strict();
export type EventContext = z.infer<typeof EventContextSchema>;

export const GateSchema = z.object({
  would_send: z.boolean(),
  reasons: z.array(
    z.enum([
      'toggle_off',
      'no_channel',
      'no_signup_channel',
      'state_not_signups_open',
      'state_not_open_or_roll_call',
      'no_signup_post_yet',
      'no_discord_server',
      'start_in_past',
      'not_a_series',
      'no_recipients',
      'series_paused',
      'series_ended',
      'already_sent',
      'no_scheduled_event_yet',
      'occurrence_collision',
    ]),
  ),
});
export type Gate = z.infer<typeof GateSchema>;

export const MentionsSchema = z.object({
  users: z.record(z.string(), z.string()),
});
export type Mentions = z.infer<typeof MentionsSchema>;

export const NewEventContextSchema = z
  .object({ type: z.literal('new_event'), organization_id: z.number().int() })
  .strict();
export type NewEventContext = z.infer<typeof NewEventContextSchema>;

export const NewRepeaterContextSchema = z
  .object({
    type: z.literal('new_repeater'),
    organization_id: z.number().int(),
  })
  .strict();
export type NewRepeaterContext = z.infer<typeof NewRepeaterContextSchema>;

export const OrgDefaultsContextSchema = z
  .object({
    type: z.literal('org_defaults'),
    organization_id: z.number().int(),
  })
  .strict();
export type OrgDefaultsContext = z.infer<typeof OrgDefaultsContextSchema>;

export const PreviewDestinationSchema = z.object({
  type: z.enum(['channel', 'forum_thread', 'dm', 'reply', 'scheduled_event']),
  channel_id: z.union([z.string(), z.null()]),
  thread_name: z.union([z.string(), z.null()]),
  fallback_channel_id: z.union([z.string(), z.null()]),
  reply_to_message_id: z.union([z.string(), z.null()]),
});
export type PreviewDestination = z.infer<typeof PreviewDestinationSchema>;

export const RepeaterContextSchema = z
  .object({ type: z.literal('repeater'), repeater_id: z.number().int() })
  .strict();
export type RepeaterContext = z.infer<typeof RepeaterContextSchema>;

export const ScheduledEventLocationSchema = z.object({ location: z.string() });
export type ScheduledEventLocation = z.infer<
  typeof ScheduledEventLocationSchema
>;

export const ScheduledEventPreviewSchema = z.object({
  name: z.string(),
  description: z.string(),
  scheduled_start_time: z.string(),
  scheduled_end_time: z.union([z.string(), z.null()]),
  entity_metadata: ScheduledEventLocationSchema,
});
export type ScheduledEventPreview = z.infer<typeof ScheduledEventPreviewSchema>;

export const SelectOptionSchema = z.object({
  label: z.string(),
  value: z.string(),
  description: z.union([z.string(), z.null()]),
  emoji: z.union([EmojiSchema, z.null()]),
  default: z.union([z.boolean(), z.null()]),
});
export type SelectOption = z.infer<typeof SelectOptionSchema>;

export const SelectMenuSchema = z.object({
  type: z.union([
    z.literal(3),
    z.literal(5),
    z.literal(6),
    z.literal(7),
    z.literal(8),
  ]),
  custom_id: z.string(),
  placeholder: z.union([z.string(), z.null()]),
  options: z.array(SelectOptionSchema),
  min_values: z.union([z.number().int(), z.null()]),
  max_values: z.union([z.number().int(), z.null()]),
  disabled: z.union([z.boolean(), z.null()]),
});
export type SelectMenu = z.infer<typeof SelectMenuSchema>;

export const ActionRowSchema = z.object({
  type: z.literal(1),
  components: z.array(
    z.any().superRefine((x, ctx) => {
      const schemas = [ButtonSchema, SelectMenuSchema];
      const { errors, failed } = schemas.reduce<{
        errors: z.core.$ZodIssue[];
        failed: number;
      }>(
        ({ errors, failed }, schema) =>
          ((result) =>
            result.error
              ? {
                  errors: [...errors, ...result.error.issues],
                  failed: failed + 1,
                }
              : { errors, failed })(schema.safeParse(x)),
        { errors: [], failed: 0 },
      );
      const passed = schemas.length - failed;
      if (passed !== 1) {
        ctx.addIssue(
          errors.length
            ? {
                path: [],
                code: 'invalid_union',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              }
            : {
                path: [],
                code: 'custom',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              },
        );
      }
    }),
  ),
});
export type ActionRow = z.infer<typeof ActionRowSchema>;

export const SeparatorSchema = z.object({
  type: z.literal(14),
  divider: z.union([z.boolean(), z.null()]),
  spacing: z.union([z.number().int(), z.null()]),
});
export type Separator = z.infer<typeof SeparatorSchema>;

export const SeriesOneOffContextSchema = z
  .object({ type: z.literal('series_one_off'), repeater_id: z.number().int() })
  .strict();
export type SeriesOneOffContext = z.infer<typeof SeriesOneOffContextSchema>;

export const DiscordPreviewRequestSchema = z
  .object({
    kind: z.enum([
      'scheduled_event',
      'scheduled_event_sync',
      'signup_reminder',
      'profile_reminder',
      'attendance_reminder',
      'start_mention',
      'signup_post',
      'announcement_notice',
      'new_event_post',
    ]),
    context: z.any().superRefine((x, ctx) => {
      const schemas = [
        EventContextSchema,
        NewEventContextSchema,
        SeriesOneOffContextSchema,
        RepeaterContextSchema,
        NewRepeaterContextSchema,
        OrgDefaultsContextSchema,
      ];
      const { errors, failed } = schemas.reduce<{
        errors: z.core.$ZodIssue[];
        failed: number;
      }>(
        ({ errors, failed }, schema) =>
          ((result) =>
            result.error
              ? {
                  errors: [...errors, ...result.error.issues],
                  failed: failed + 1,
                }
              : { errors, failed })(schema.safeParse(x)),
        { errors: [], failed: 0 },
      );
      const passed = schemas.length - failed;
      if (passed !== 1) {
        ctx.addIssue(
          errors.length
            ? {
                path: [],
                code: 'invalid_union',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              }
            : {
                path: [],
                code: 'custom',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              },
        );
      }
    }),
    values: z.record(z.string(), z.any()),
    open_signups: z.boolean(),
  })
  .strict();
export type DiscordPreviewRequest = z.infer<typeof DiscordPreviewRequestSchema>;

export const TextDisplaySchema = z.object({
  type: z.literal(10),
  content: z.string(),
});
export type TextDisplay = z.infer<typeof TextDisplaySchema>;

export const UnfurledMediaSchema = z.object({ url: z.string() });
export type UnfurledMedia = z.infer<typeof UnfurledMediaSchema>;

export const MediaGalleryItemSchema = z.object({
  media: UnfurledMediaSchema,
  description: z.union([z.string(), z.null()]),
  spoiler: z.union([z.boolean(), z.null()]),
});
export type MediaGalleryItem = z.infer<typeof MediaGalleryItemSchema>;

export const MediaGallerySchema = z.object({
  type: z.literal(12),
  items: z.array(MediaGalleryItemSchema),
});
export type MediaGallery = z.infer<typeof MediaGallerySchema>;

export const ThumbnailSchema = z.object({
  type: z.literal(11),
  media: UnfurledMediaSchema,
  description: z.union([z.string(), z.null()]),
  spoiler: z.union([z.boolean(), z.null()]),
});
export type Thumbnail = z.infer<typeof ThumbnailSchema>;

export const SectionSchema = z.object({
  type: z.literal(9),
  components: z.array(TextDisplaySchema),
  accessory: z.any().superRefine((x, ctx) => {
    const schemas = [ThumbnailSchema, ButtonSchema];
    const { errors, failed } = schemas.reduce<{
      errors: z.core.$ZodIssue[];
      failed: number;
    }>(
      ({ errors, failed }, schema) =>
        ((result) =>
          result.error
            ? {
                errors: [...errors, ...result.error.issues],
                failed: failed + 1,
              }
            : { errors, failed })(schema.safeParse(x)),
      { errors: [], failed: 0 },
    );
    const passed = schemas.length - failed;
    if (passed !== 1) {
      ctx.addIssue(
        errors.length
          ? {
              path: [],
              code: 'invalid_union',
              errors: [errors],
              message:
                'Invalid input: Should pass single schema. Passed ' + passed,
            }
          : {
              path: [],
              code: 'custom',
              errors: [errors],
              message:
                'Invalid input: Should pass single schema. Passed ' + passed,
            },
      );
    }
  }),
});
export type Section = z.infer<typeof SectionSchema>;

export const ContainerSchema = z.object({
  type: z.literal(17),
  accent_color: z.union([z.number().int(), z.null()]),
  spoiler: z.union([z.boolean(), z.null()]),
  components: z.array(
    z.any().superRefine((x, ctx) => {
      const schemas = [
        ActionRowSchema,
        SectionSchema,
        TextDisplaySchema,
        SeparatorSchema,
        MediaGallerySchema,
      ];
      const { errors, failed } = schemas.reduce<{
        errors: z.core.$ZodIssue[];
        failed: number;
      }>(
        ({ errors, failed }, schema) =>
          ((result) =>
            result.error
              ? {
                  errors: [...errors, ...result.error.issues],
                  failed: failed + 1,
                }
              : { errors, failed })(schema.safeParse(x)),
        { errors: [], failed: 0 },
      );
      const passed = schemas.length - failed;
      if (passed !== 1) {
        ctx.addIssue(
          errors.length
            ? {
                path: [],
                code: 'invalid_union',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              }
            : {
                path: [],
                code: 'custom',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              },
        );
      }
    }),
  ),
});
export type Container = z.infer<typeof ContainerSchema>;

export const DiscordMessageSchema = z.object({
  content: z.union([z.string(), z.null()]),
  embeds: z.array(EmbedSchema),
  components: z.array(
    z.any().superRefine((x, ctx) => {
      const schemas = [
        ActionRowSchema,
        ContainerSchema,
        SectionSchema,
        TextDisplaySchema,
        SeparatorSchema,
        MediaGallerySchema,
      ];
      const { errors, failed } = schemas.reduce<{
        errors: z.core.$ZodIssue[];
        failed: number;
      }>(
        ({ errors, failed }, schema) =>
          ((result) =>
            result.error
              ? {
                  errors: [...errors, ...result.error.issues],
                  failed: failed + 1,
                }
              : { errors, failed })(schema.safeParse(x)),
        { errors: [], failed: 0 },
      );
      const passed = schemas.length - failed;
      if (passed !== 1) {
        ctx.addIssue(
          errors.length
            ? {
                path: [],
                code: 'invalid_union',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              }
            : {
                path: [],
                code: 'custom',
                errors: [errors],
                message:
                  'Invalid input: Should pass single schema. Passed ' + passed,
              },
        );
      }
    }),
  ),
  allowed_mentions: z.union([z.record(z.string(), z.any()), z.null()]),
  flags: z.union([z.number().int(), z.null()]),
});
export type DiscordMessage = z.infer<typeof DiscordMessageSchema>;

export const VariantSchema = z.object({
  code: z.literal('current_post'),
  messages: z.array(DiscordMessageSchema),
});
export type Variant = z.infer<typeof VariantSchema>;

export const DiscordPreviewResponseSchema = z.object({
  kind: z.enum([
    'scheduled_event',
    'scheduled_event_sync',
    'signup_reminder',
    'profile_reminder',
    'attendance_reminder',
    'start_mention',
    'signup_post',
    'announcement_notice',
    'new_event_post',
  ]),
  status: z.enum(['ok', 'needs_input', 'unavailable']),
  missing: z.array(z.string()),
  saved: z.boolean(),
  gate: GateSchema,
  destination: z.union([PreviewDestinationSchema, z.null()]),
  messages: z.array(DiscordMessageSchema),
  variants: z.array(VariantSchema),
  scheduled_event: z.union([ScheduledEventPreviewSchema, z.null()]),
  notes: z.array(
    z.enum([
      'edits_refresh_embed_only',
      'fallback_drops_role_mentions',
      'signup_link_points_to_post',
      'unsaved_links',
      'sync_overwrites_description',
      'dm_per_subscriber',
      'shown_as_posted_when_signups_open',
      'fallback_replaces_notice',
      'signup_post_in_signup_channel',
      'notice_falls_back_if_signup_post_fails',
      'next_event_already_open_not_updated',
      'existing_event_still_posts',
    ]),
  ),
  note_args: z.record(z.string(), z.string()),
  mentions: MentionsSchema,
});
export type DiscordPreviewResponse = z.infer<
  typeof DiscordPreviewResponseSchema
>;

export const DiscordPreviewApiSchema = z.object({
  request: DiscordPreviewRequestSchema,
  response: DiscordPreviewResponseSchema,
});
export type DiscordPreviewApi = z.infer<typeof DiscordPreviewApiSchema>;
