import { beforeEach, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import {
  getEventPermissionChecks,
  postEventPermissionChecks,
  postOrgPermissionChecks,
} from '../api';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { get, post } }));
const body = {
  refresh: true,
  checks: [
    {
      key: 'post',
      action: 'announcement' as const,
      channel_id: null,
      include_rsvp: false,
    },
  ],
};
beforeEach(() => {
  vi.resetAllMocks();
  get.mockResolvedValue({ data: fixture });
  post.mockResolvedValue({ data: fixture });
});
it('parses the shared backend response and forwards abort signals', async () => {
  const signal = new AbortController().signal;
  expect(await postOrgPermissionChecks(7, body, signal)).toEqual(fixture);
  expect(post).toHaveBeenCalledWith(
    '/discord/organizations/7/permission-checks/',
    body,
    { signal },
  );
  expect(await postEventPermissionChecks(9, body)).toEqual(fixture);
  expect(post).toHaveBeenLastCalledWith('/events/9/permission-checks/', body, {
    signal: undefined,
  });
  expect(await getEventPermissionChecks(9, true, signal)).toEqual(fixture);
  expect(get).toHaveBeenCalledWith('/events/9/permission-checks/', {
    params: { refresh: true },
    signal,
  });
});
it('rejects malformed successful responses', async () => {
  get.mockResolvedValue({ data: {} });
  post.mockResolvedValue({ data: {} });
  await expect(getEventPermissionChecks(9)).rejects.toBeInstanceOf(ZodError);
  await expect(postEventPermissionChecks(9, body)).rejects.toBeInstanceOf(
    ZodError,
  );
  await expect(postOrgPermissionChecks(7, body)).rejects.toBeInstanceOf(
    ZodError,
  );
});
