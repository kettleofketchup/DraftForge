import type { DiscordPreviewContext } from './context';
import type { PreviewKind } from './schemas';

export const eventDiscordPreviewKeys = {
  all: ['event-discord-preview'] as const,
  preview: (
    kind: PreviewKind,
    context: DiscordPreviewContext,
    viewerId: number | undefined,
  ) =>
    [...eventDiscordPreviewKeys.all, kind, context, viewerId ?? null] as const,
};
