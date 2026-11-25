// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AutoAssignModal } from '../AutoAssignModal';

const { api, toast } = vi.hoisted(() => ({
  api: { post: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

vi.mock('~/components/api/axios', () => ({ api }));
vi.mock('sonner', () => ({ toast }));

const preview = {
  assignments: [
    {
      game_id: 5,
      game_round: 1,
      game_position: 0,
      bracket_type: 'winners',
      match_id: 9,
      start_time: 1764072000,
      start_time_display: '12:00',
      player_overlap: 10,
      radiant_team: 'Team A',
      dire_team: 'Team B',
      radiant_captain: null,
      dire_captain: null,
      radiant_game_num: null,
      dire_game_num: null,
      match_method: 'captain_sequence',
    },
  ],
  tournament_date: '2026-11-25',
  total_unlinked_games: 1,
  total_candidate_matches: 1,
};

function mockApply(skipped: unknown[]) {
  api.post.mockImplementation((_url: string, body: { apply?: boolean }) =>
    Promise.resolve({
      data: body.apply
        ? {
            ...preview,
            assignments: [],
            linked_count: 1,
            skipped_roster_conflicts: skipped,
          }
        : preview,
    }),
  );
}

async function renderAndApply() {
  const onAssignComplete = vi.fn();
  render(
    <AutoAssignModal
      isOpen
      onClose={vi.fn()}
      tournamentId={7}
      onAssignComplete={onAssignComplete}
    />,
  );
  const apply = await screen.findByRole('button', {
    name: /Apply 1 Assignments/,
  });
  fireEvent.click(apply);
  return onAssignComplete;
}

describe('AutoAssignModal apply', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('warns when games were skipped over a roster conflict', async () => {
    mockApply([{ game_id: 5, match_id: 9, team_id: 2, user_ids: [3] }]);
    const onAssignComplete = await renderAndApply();

    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith(
        'Linked 1 matches; skipped 1: a player would be on two live teams',
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(onAssignComplete).toHaveBeenCalled();
  });

  it('reports success when nothing was skipped', async () => {
    mockApply([]);
    await renderAndApply();

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('Linked 1 matches'),
    );
    expect(toast.warning).not.toHaveBeenCalled();
  });
});
