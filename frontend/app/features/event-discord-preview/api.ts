import { ZodError } from 'zod';
import api from '~/components/api/axios';
import { getLogger } from '~/lib/logger';
import {
  DiscordPreviewResponseSchema,
  type DiscordPreviewRequest,
  type DiscordPreviewResponse,
} from './schemas';

const log = getLogger('event-discord-preview');

export async function previewEventDiscordMessage(
  req: DiscordPreviewRequest,
): Promise<DiscordPreviewResponse> {
  const { data } = await api.post('/events/discord-preview/', req);
  try {
    return DiscordPreviewResponseSchema.parse(data);
  } catch (err) {
    if (err instanceof ZodError)
      log.error('discord preview response did not match schema', {
        kind: req.kind,
        issues: err.issues,
      });
    throw err;
  }
}
