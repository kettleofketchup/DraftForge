// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getTournamentViewer } = vi.hoisted(() => ({
  getTournamentViewer: vi.fn(),
}));

vi.mock('~/features/tournament-viewer/api', () => ({ getTournamentViewer }));

import type { TournamentType } from '~/components/tournament/types';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useUserStore } from '~/store/userStore';
import { CreateTeamsButton } from '../createTeamsButton';

const tournament = {
  pk: 11,
  name: 'Cup',
  teams: [],
} as unknown as TournamentType;

function renderButton() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <CreateTeamsButton
          tournament={tournament}
          teams={[]}
          dialogOpen
          setDialogOpen={() => {}}
        />
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getTournamentViewer.mockReset();
  // Not site staff: the tournament-edit flag alone must decide.
  useUserStore.setState({
    currentUser: { pk: 42, username: 'viewer', is_staff: false },
  } as never);
});

describe('CreateTeamsButton', () => {
  it('shows the submit button to org or league staff of the tournament', async () => {
    getTournamentViewer.mockResolvedValue({ can_edit_tournament: true });

    renderButton();

    expect(await screen.findByTestId('submitTeamsBtn')).toBeTruthy();
    expect(getTournamentViewer).toHaveBeenCalledWith(11);
  });

  it('hides the submit button from a player', async () => {
    getTournamentViewer.mockResolvedValue({ can_edit_tournament: false });

    renderButton();

    expect(await screen.findByText('Must be Admin')).toBeTruthy();
    expect(screen.queryByTestId('submitTeamsBtn')).toBeNull();
  });
});
