import { beforeEach, describe, expect, it, vi } from 'vitest';
import { extractApiError } from '~/lib/apiError';
import { previewResponse } from './fixtures';

const mocks = vi.hoisted(() => ({ post: vi.fn(), error: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { post: mocks.post } }));
vi.mock('~/lib/logger', () => ({
  getLogger: () => ({ error: mocks.error, warn: vi.fn(), info: vi.fn() }),
}));

import { previewEventDiscordMessage } from '../api';

const req = {
  kind: 'signup_post' as const,
  context: { type: 'event' as const, event_id: 42 },
  values: { name: 'Friday' },
  open_signups: false,
};

beforeEach(() => {
  mocks.post.mockReset();
  mocks.error.mockReset();
});

describe('previewEventDiscordMessage', () => {
  it('posts the request and returns the parsed preview', async () => {
    mocks.post.mockResolvedValue({ data: previewResponse() });
    await expect(previewEventDiscordMessage(req)).resolves.toEqual(
      previewResponse(),
    );
    expect(mocks.post).toHaveBeenCalledWith('/events/discord-preview/', req);
  });

  it('logs and rethrows a malformed payload', async () => {
    mocks.post.mockResolvedValue({ data: { kind: 'signup_post' } });
    await expect(previewEventDiscordMessage(req)).rejects.toThrow();
    expect(mocks.error).toHaveBeenCalledOnce();
  });

  it('surfaces the readable sentence of a preview 400', async () => {
    const err = {
      response: {
        status: 400,
        data: { error: 'Invalid preview request.', detail: [{ loc: ['x'] }] },
      },
    };
    mocks.post.mockRejectedValue(err);
    const caught = await previewEventDiscordMessage(req).catch((e) => e);
    expect(extractApiError(caught)).toBe('Invalid preview request.');
  });

  it('surfaces the first DRF field error', async () => {
    const err = {
      response: {
        status: 400,
        data: { max_players: ['A valid integer is required.'] },
      },
    };
    mocks.post.mockRejectedValue(err);
    const caught = await previewEventDiscordMessage(req).catch((e) => e);
    expect(extractApiError(caught)).toBe('A valid integer is required.');
  });
});
