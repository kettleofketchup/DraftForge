// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { TeamPlacementControl } from '../TeamPlacementControl';
import { teamManageKeys } from '../useTeamManagement';
import { axiosError, invalidatedKeys, stubRadix } from './manageDialogHarness';

const axiosMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));
vi.mock('~/components/api/axios', () => ({
  default: axiosMock,
  api: axiosMock,
}));

const logger = vi.hoisted(() => ({
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}));
vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));

const TOURNAMENT = 11;
const TEAM = 22;
const PATH = `/bracket/tournaments/${TOURNAMENT}/teams/${TEAM}/placement/`;

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  axiosMock.patch.mockReset();
});

function renderControl(placement: number | null) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  render(
    <QueryClientProvider client={queryClient}>
      <TeamPlacementControl
        tournamentId={TOURNAMENT}
        teamId={TEAM}
        placement={placement}
      />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByTestId('team-placement-trigger'));
  return { invalidate };
}

const input = () => screen.getByTestId('team-placement-input');
const save = () => screen.getByTestId('team-placement-save');
const clear = () => screen.getByTestId('team-placement-clear');
const type = (value: string) =>
  fireEvent.change(input(), { target: { value } });

describe('TeamPlacementControl', () => {
  it('Save PATCHes the placement and refreshes the team and tournament', async () => {
    axiosMock.patch.mockResolvedValueOnce({
      data: { team_id: TEAM, placement: 3 },
    });
    const { invalidate } = renderControl(null);
    type('3');
    fireEvent.click(save());
    await waitFor(() =>
      expect(axiosMock.patch).toHaveBeenCalledWith(PATH, { placement: 3 }),
    );
    await waitFor(() =>
      expect(invalidatedKeys(invalidate)).toEqual(
        expect.arrayContaining([
          ['tournament', TOURNAMENT],
          teamManageKeys.managed(TEAM),
        ]),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByTestId('team-placement-input')).toBeNull(),
    );
  });

  it('prefills the current placement', () => {
    renderControl(4);
    expect(input()).toHaveValue(4);
  });

  it('Clear PATCHes a null placement', async () => {
    axiosMock.patch.mockResolvedValueOnce({
      data: { team_id: TEAM, placement: null },
    });
    renderControl(2);
    fireEvent.click(clear());
    await waitFor(() =>
      expect(axiosMock.patch).toHaveBeenCalledWith(PATH, { placement: null }),
    );
  });

  it('disables Clear on a team that is still in the tournament', () => {
    renderControl(null);
    expect(clear()).toBeDisabled();
  });

  it('placement control rejects 0 and blank', () => {
    renderControl(null);
    expect(save()).toBeDisabled();
    for (const bad of ['', '0', '-2', '1.5', '  ']) {
      type(bad);
      expect(save()).toBeDisabled();
    }
    fireEvent.click(save());
    expect(axiosMock.patch).not.toHaveBeenCalled();
    type('1');
    expect(save()).not.toBeDisabled();
  });

  it('shows a 409 roster_conflict message inline', async () => {
    const error =
      'roster_c also play for Others. Resolve that before reopening this team.';
    axiosMock.patch.mockRejectedValueOnce(
      axiosError(409, {
        code: 'roster_conflict',
        error,
        details: { team_id: TEAM, user_ids: [2] },
      }),
    );
    renderControl(2);
    fireEvent.click(clear());
    expect(await screen.findByTestId('team-placement-error')).toHaveTextContent(
      error,
    );
    expect(logger.warn).toHaveBeenCalledWith('Team placement refused', {
      teamId: TEAM,
      status: 409,
      code: 'roster_conflict',
    });
    expect(input()).toBeTruthy();
  });

  it('shows a 403 message inline', async () => {
    axiosMock.patch.mockRejectedValueOnce(
      axiosError(403, {
        detail: 'You do not have permission to modify this tournament.',
      }),
    );
    renderControl(null);
    type('2');
    fireEvent.click(save());
    expect(await screen.findByTestId('team-placement-error')).toHaveTextContent(
      'You do not have permission to modify this tournament.',
    );
  });
});
