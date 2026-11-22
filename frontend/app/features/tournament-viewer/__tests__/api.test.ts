import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getTournamentViewer } from '../api';

beforeEach(() => {
  get.mockReset();
});

describe('getTournamentViewer', () => {
  it('requests the viewer endpoint and parses the flag', async () => {
    get.mockResolvedValue({ data: { can_edit_tournament: true } });

    await expect(getTournamentViewer(7)).resolves.toEqual({
      can_edit_tournament: true,
    });
    expect(get).toHaveBeenCalledWith('/tournaments/7/viewer/');
  });

  it('rejects a malformed body', async () => {
    get.mockResolvedValue({ data: { can_edit_tournament: 'yes' } });

    await expect(getTournamentViewer(7)).rejects.toBeInstanceOf(ZodError);
  });
});
