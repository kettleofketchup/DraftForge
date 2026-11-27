import { AxiosError } from 'axios';
import { expect, it, vi } from 'vitest';
import { ZodError } from 'zod';
import { getEventDiscordState } from '../eventsAPI';
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('../axios', () => ({ default: { get } }));
it('returns null only for a missing Discord state', async () => {
  const error = new AxiosError('missing');
  error.response = { status: 404 } as NonNullable<AxiosError['response']>;
  get.mockRejectedValueOnce(error);
  expect(await getEventDiscordState(9)).toBeNull();
});
it('rethrows server and network failures', async () => {
  const error = new AxiosError('server');
  error.response = { status: 500 } as NonNullable<AxiosError['response']>;
  get.mockRejectedValueOnce(error);
  await expect(getEventDiscordState(9)).rejects.toBe(error);
  const network = new Error('offline');
  get.mockRejectedValueOnce(network);
  await expect(getEventDiscordState(9)).rejects.toBe(network);
});
it('rejects malformed successful state', async () => {
  get.mockResolvedValueOnce({ data: {} });
  await expect(getEventDiscordState(9)).rejects.toBeInstanceOf(ZodError);
});
