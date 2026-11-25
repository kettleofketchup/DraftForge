import type { DiscordPreviewResponse } from '../schemas';

export function previewResponse(
  overrides: Partial<DiscordPreviewResponse> = {},
): DiscordPreviewResponse {
  return {
    kind: 'signup_post',
    status: 'ok',
    missing: [],
    saved: true,
    gate: { would_send: true, reasons: [] },
    destination: {
      type: 'forum_thread',
      channel_id: '1234',
      thread_name: 'Friday Inhouse',
      fallback_channel_id: '5678',
      reply_to_message_id: null,
    },
    messages: [
      {
        content: '<@&111>',
        embeds: [],
        components: [],
        allowed_mentions: { roles: ['111'] },
        flags: null,
      },
    ],
    variants: [],
    scheduled_event: null,
    notes: [],
    note_args: {},
    mentions: { users: {} },
    ...overrides,
  };
}
