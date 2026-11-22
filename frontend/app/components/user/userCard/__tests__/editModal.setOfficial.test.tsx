// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LeagueType } from '~/components/league/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserClassType } from '~/components/user/types';
import { UserEditModal } from '../editModal';
import type { EditUserScope } from '../editUserSchema';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('../editForm', () => ({ UserEditForm: () => null }));
vi.mock('../editUserSchema', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../editUserSchema')>();
  return { ...actual, useScopedEditPermission: () => true };
});
vi.mock('~/features/mmr-requests', () => ({
  SetOfficialMmrDialog: (props: {
    open: boolean;
    scope: object;
    member: object;
  }) =>
    props.open ? (
      <div data-testid="set-official-dialog-stub">
        {JSON.stringify({ scope: props.scope, member: props.member })}
      </div>
    ) : null,
}));

const USER = {
  pk: 42,
  username: 'member',
  nickname: 'Member',
  orgUserPk: 117,
} as UserClassType;

const ORG_SCOPE: EditUserScope = {
  kind: 'org',
  organization: { pk: 3, name: 'Org X' } as OrganizationType,
};
const LEAGUE_SCOPE: EditUserScope = {
  kind: 'league',
  league: { pk: 5, name: 'Season 4' } as LeagueType,
};

function renderModal(scope: EditUserScope) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>
        <UserEditModal user={USER} scope={scope} />
      </TooltipProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByTestId('edit-user-btn'));
}

describe('UserEditModal set official MMR', () => {
  it('offers the button in org scope and opens the dialog prefilled', async () => {
    renderModal(ORG_SCOPE);
    fireEvent.click(await screen.findByTestId('set-official-mmr-btn'));
    const stub = await screen.findByTestId('set-official-dialog-stub');
    expect(JSON.parse(stub.textContent!)).toEqual({
      scope: { org: 3 },
      member: { userPk: 42, orgUserPk: 117, name: 'Member' },
    });
  });

  it('offers the button in league scope', async () => {
    renderModal(LEAGUE_SCOPE);
    fireEvent.click(await screen.findByTestId('set-official-mmr-btn'));
    const stub = await screen.findByTestId('set-official-dialog-stub');
    expect(JSON.parse(stub.textContent!).scope).toEqual({ league: 5 });
  });

  it('has no button in global scope', async () => {
    renderModal({ kind: 'global' });
    expect(await screen.findByTestId('edit-user-modal')).toBeInTheDocument();
    expect(
      screen.queryByTestId('set-official-mmr-btn'),
    ).not.toBeInTheDocument();
  });
});
