// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deleteTournament } from '~/components/api/api';
import { TooltipProvider } from '~/components/ui/tooltip';
import { useUserStore } from '~/store/userStore';
import { TournamentRemoveButton } from '../card/deleteButton';
import { refreshAfterSave } from '../create/editForm';
import type { TournamentType } from '../types';

vi.mock('~/components/api/api');

describe('TournamentRemoveButton', () => {
  beforeEach(() => {
    vi.mocked(deleteTournament).mockResolvedValue(undefined as never);
    useUserStore.setState({
      currentUser: { pk: 1, username: 'staff', is_staff: true },
      isStaff: () => true,
      delTournament: vi.fn(),
    } as never);
  });

  it('invalidates the tournaments queries after a delete', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const spy = vi.spyOn(client, 'invalidateQueries');
    const tournament = { pk: 42, name: 'Doomed' } as TournamentType;

    render(
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <TournamentRemoveButton tournament={tournament} />
        </TooltipProvider>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Delete tournament' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm Delete' }));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ['tournaments'] }),
    );
    expect(deleteTournament).toHaveBeenCalledWith(42);
  });
});

describe('refreshAfterSave', () => {
  function setup() {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const getTournaments = vi.fn();
    return { queryClient, invalidate, getTournaments };
  }

  it.each(['/tournaments', '/tournaments/'])(
    'skips the store refresh on %s',
    (pathname) => {
      const { queryClient, invalidate, getTournaments } = setup();
      refreshAfterSave({ pathname, getTournaments, queryClient });
      expect(getTournaments).not.toHaveBeenCalled();
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ['tournaments'] });
    },
  );

  it('refreshes the store elsewhere', () => {
    const { queryClient, invalidate, getTournaments } = setup();
    refreshAfterSave({ pathname: '/leagues/3', getTournaments, queryClient });
    expect(getTournaments).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['tournaments'] });
  });

  it('invalidates the single tournament when a pk is given', () => {
    const { queryClient, invalidate, getTournaments } = setup();
    refreshAfterSave({ pathname: '/leagues/3', getTournaments, queryClient, pk: 9 });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['tournament', 9] });
  });

  it('does not invalidate a single tournament without a pk', () => {
    const { queryClient, invalidate, getTournaments } = setup();
    refreshAfterSave({ pathname: '/tournaments', getTournaments, queryClient });
    expect(invalidate).toHaveBeenCalledTimes(1);
  });
});
