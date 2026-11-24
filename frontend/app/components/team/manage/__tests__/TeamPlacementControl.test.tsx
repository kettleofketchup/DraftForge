// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { placementEffect, TeamPlacementControl } from '../TeamPlacementControl';
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
const TEAM_NAME = 'TM Delta';
const REASON = 'lost the lower final';
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
        teamName={TEAM_NAME}
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
const confirm = () => screen.getByTestId('team-placement-confirm');
const giveReason = (value = REASON) =>
  fireEvent.change(screen.getByTestId('team-placement-reason'), {
    target: { value },
  });

describe('TeamPlacementControl', () => {
  it('Save PATCHes the placement and refreshes the team and tournament', async () => {
    axiosMock.patch.mockResolvedValueOnce({
      data: { team_id: TEAM, placement: 3 },
    });
    const { invalidate } = renderControl(null);
    type('3');
    fireEvent.click(save());
    expect(axiosMock.patch).not.toHaveBeenCalled();
    expect(screen.getByTestId('team-placement-confirm-text')).toHaveTextContent(
      `Mark ${TEAM_NAME} eliminated (3rd)? It leaves the tournament and its players become free to join other teams.`,
    );
    expect(confirm()).toBeDisabled();
    giveReason();
    fireEvent.click(confirm());
    await waitFor(() =>
      expect(axiosMock.patch).toHaveBeenCalledWith(PATH, {
        placement: 3,
        reason: REASON,
      }),
    );
    await waitFor(() =>
      expect(invalidatedKeys(invalidate)).toEqual(
        expect.arrayContaining([
          ['tournament', TOURNAMENT],
          teamManageKeys.managed(TEAM),
          teamManageKeys.history(TEAM),
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
    expect(screen.getByTestId('team-placement-confirm-text')).toHaveTextContent(
      `Put ${TEAM_NAME} back in the tournament?`,
    );
    giveReason();
    fireEvent.click(confirm());
    await waitFor(() =>
      expect(axiosMock.patch).toHaveBeenCalledWith(PATH, {
        placement: null,
        reason: REASON,
      }),
    );
  });

  it('Back returns to the placement form without saving', () => {
    renderControl(null);
    type('4');
    fireEvent.click(save());
    fireEvent.click(screen.getByTestId('team-placement-back'));
    expect(input()).toHaveValue(4);
    expect(axiosMock.patch).not.toHaveBeenCalled();
  });

  it('needs a reason of at least 3 characters', () => {
    renderControl(null);
    type('4');
    fireEvent.click(save());
    giveReason('  ab ');
    expect(confirm()).toBeDisabled();
    giveReason('abc');
    expect(confirm()).not.toBeDisabled();
  });

  it('disables Save when the placement is unchanged', () => {
    renderControl(4);
    expect(save()).toBeDisabled();
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
    giveReason();
    fireEvent.click(confirm());
    expect(await screen.findByTestId('team-placement-error')).toHaveTextContent(
      error,
    );
    expect(logger.warn).toHaveBeenCalledWith('Team placement refused', {
      teamId: TEAM,
      status: 409,
      code: 'roster_conflict',
    });
    expect(confirm()).toBeTruthy();
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
    giveReason();
    fireEvent.click(confirm());
    expect(await screen.findByTestId('team-placement-error')).toHaveTextContent(
      'You do not have permission to modify this tournament.',
    );
  });
});

describe('placementEffect', () => {
  it('names the winner', () => {
    expect(placementEffect('A', null, 1).question).toBe(
      'Mark A the winner (1st)? It leaves the tournament and its players become free to join other teams.',
    );
  });

  it('describes a change between placements', () => {
    expect(placementEffect('A', 4, 3)).toEqual({
      question: "Change A's placement from 4th to 3rd?",
      confirmText: 'Change placement',
    });
  });
});
