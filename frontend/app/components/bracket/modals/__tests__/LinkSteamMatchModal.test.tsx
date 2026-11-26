// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BracketMatch } from '../../types';
import { LinkSteamMatchModal } from '../LinkSteamMatchModal';

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('~/components/api/axios', () => ({ api }));
vi.mock('sonner', () => ({ toast }));
vi.mock('~/store/userStore', async () => {
  const { create } = await import('zustand');
  return { useUserStore: create(() => ({ tournament: { pk: 7 } })) };
});
vi.mock('../DotaMatchStatsModal', () => ({ DotaMatchStatsModal: () => null }));

const CONFLICT =
  'ko_p1 also play for Team C. Resolve that before reopening this team.';

const game: BracketMatch = {
  id: 'w-1-0',
  gameId: 42,
  round: 1,
  position: 0,
  bracketType: 'winners',
  eliminationType: 'single',
  status: 'completed',
};

function conflictError(): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError(
    'Request failed with status code 409',
    '409',
    config,
    null,
    {
      status: 409,
      statusText: 'Conflict',
      headers: {},
      config,
      data: {
        code: 'roster_conflict',
        error: CONFLICT,
        details: { team_id: 1, user_ids: [2] },
      },
    },
  );
}

async function renderLinked() {
  const onLinkUpdated = vi.fn();
  render(
    <LinkSteamMatchModal
      isOpen
      onClose={vi.fn()}
      game={game}
      onLinkUpdated={onLinkUpdated}
    />,
  );
  await screen.findByTestId('currently-linked', {}, { timeout: 2000 });
  return onLinkUpdated;
}

describe('LinkSteamMatchModal unlink', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({
      data: { suggestions: [], linked_match_id: 8922000001 },
    });
  });

  it('shows the roster conflict when the unlink is refused', async () => {
    api.delete.mockRejectedValue(conflictError());
    const onLinkUpdated = await renderLinked();

    fireEvent.click(screen.getByTestId('unlink-btn'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        `Failed to unlink match: ${CONFLICT}`,
      ),
    );
    expect(onLinkUpdated).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(screen.getByTestId('currently-linked')).toHaveTextContent(
      'Match #8922000001',
    );
  });

  it('keeps the generic message for other failures', async () => {
    api.delete.mockRejectedValue(new Error('boom'));
    await renderLinked();

    fireEvent.click(screen.getByTestId('unlink-btn'));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'Failed to unlink match. Are you logged in as staff?',
      ),
    );
  });
});
