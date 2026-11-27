import type { Button, SelectMenu } from './types';

type Opt<T> = T | null | undefined;

export type EmojiInput = {
  id?: Opt<string>;
  name?: Opt<string>;
  animated?: Opt<boolean>;
};

export type EmbedFieldInput = {
  name: string;
  value: string;
  inline?: Opt<boolean>;
};

export type EmbedInput = {
  title?: Opt<string>;
  description?: Opt<string>;
  url?: Opt<string>;
  color?: Opt<number>;
  timestamp?: Opt<string>;
  author?: Opt<{ name: string; url?: Opt<string>; icon_url?: Opt<string> }>;
  footer?: Opt<{ text: string; icon_url?: Opt<string> }>;
  thumbnail?: Opt<{ url: string }>;
  image?: Opt<{ url: string }>;
  fields?: EmbedFieldInput[];
};

export type ButtonInput = {
  type: 2;
  style: Button['style'];
  label?: Opt<string>;
  emoji?: Opt<EmojiInput>;
  url?: Opt<string>;
  custom_id?: Opt<string>;
  disabled?: Opt<boolean>;
};

export type SelectOptionInput = {
  label: string;
  value: string;
  description?: Opt<string>;
  emoji?: Opt<EmojiInput>;
  default?: Opt<boolean>;
};

export type SelectMenuInput = {
  type: SelectMenu['type'];
  custom_id?: Opt<string>;
  placeholder?: Opt<string>;
  options?: SelectOptionInput[];
  min_values?: Opt<number>;
  max_values?: Opt<number>;
  disabled?: Opt<boolean>;
};

export type ActionRowInput = {
  type: 1;
  components: (ButtonInput | SelectMenuInput)[];
};

export type TextDisplayInput = { type: 10; content: string };

export type UnfurledMediaInput = { url: string };

export type ThumbnailInput = {
  type: 11;
  media: UnfurledMediaInput;
  description?: Opt<string>;
  spoiler?: Opt<boolean>;
};

export type SectionInput = {
  type: 9;
  components: TextDisplayInput[];
  accessory: ThumbnailInput | ButtonInput;
};

export type SeparatorInput = {
  type: 14;
  divider?: Opt<boolean>;
  spacing?: Opt<number>;
};

export type MediaGalleryItemInput = {
  media: UnfurledMediaInput;
  description?: Opt<string>;
  spoiler?: Opt<boolean>;
};

export type MediaGalleryInput = { type: 12; items: MediaGalleryItemInput[] };

export type ContainerChildInput =
  | ActionRowInput
  | SectionInput
  | TextDisplayInput
  | SeparatorInput
  | MediaGalleryInput;

export type ContainerInput = {
  type: 17;
  accent_color?: Opt<number>;
  spoiler?: Opt<boolean>;
  components: ContainerChildInput[];
};

export type TopLevelComponentInput = ContainerChildInput | ContainerInput;

export type DiscordMessageInput = {
  content?: Opt<string>;
  embeds?: EmbedInput[];
  components?: TopLevelComponentInput[];
  flags?: Opt<number>;
};

export type NormalizedMessage = {
  content: string | null;
  embeds: EmbedInput[];
  components: TopLevelComponentInput[];
  flags: number | null;
};

export function normalizeMessage(m: DiscordMessageInput): NormalizedMessage {
  return {
    content: m.content ?? null,
    embeds: m.embeds ?? [],
    components: m.components ?? [],
    flags: m.flags ?? null,
  };
}
