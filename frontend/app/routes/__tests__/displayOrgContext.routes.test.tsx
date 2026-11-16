// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import {
  createMemoryRouter,
  MemoryRouter,
  Route,
  RouterProvider,
  Routes,
} from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useOrganization } from '~/components/organization';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { UserStrip } from '~/components/user/UserStrip';
import { useDisplayOrgId } from '~/hooks/useDisplayOrgId';
import {
  CurrentTournamentDisplayOrg,
  HeroDraftDisplayOrg,
  LeagueDisplayOrg,
  OrgParamDisplayOrg,
  TournamentDisplayOrg,
} from '~/lib/displayOrgShells';
import { useHeroDraftStore } from '~/store/heroDraftStore';
import { useOrgStore } from '~/store/orgStore';
import { useUserCacheStore } from '~/store/userCacheStore';
import { useUserStore } from '~/store/userStore';

import EventDisplayOrgLayout from '../eventLayout';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  fetchOrganization: vi.fn(async (pk: number) => ({ pk, name: `Org ${pk}` })),
}));

vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useEvent: (id: number | null) => ({
    data: id === 5 ? { pk: 5, organization: 7 } : undefined,
  }),
}));

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};

function Probe() {
  return <span data-testid="probe">{String(useDisplayOrgId())}</span>;
}

const probe = () => screen.getByTestId('probe').textContent;

function OtherOrgChild() {
  useOrganization(9);
  return <Probe />;
}

function withQuery(children: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  useUserCacheStore.getState().reset();
  useOrgStore.getState().setCurrentOrg(null);
  useHeroDraftStore.setState({ draft: null });
  useUserStore.getState().setTournament(null);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('TournamentDisplayOrg', () => {
  it("provides the tournament's organization", () => {
    render(
      <TournamentDisplayOrg tournament={{ organization_pk: 7 }}>
        <Probe />
      </TournamentDisplayOrg>,
    );
    expect(probe()).toBe('7');
  });

  it('is global without a tournament org', () => {
    render(
      <TournamentDisplayOrg tournament={{ organization_pk: null }}>
        <Probe />
      </TournamentDisplayOrg>,
    );
    expect(probe()).toBe('null');
  });

  it('ignores a nested useOrganization for another org', async () => {
    render(
      withQuery(
        <TournamentDisplayOrg tournament={{ organization_pk: 7 }}>
          <OtherOrgChild />
        </TournamentDisplayOrg>,
      ),
    );
    await waitFor(() => expect(useOrgStore.getState().currentOrg?.pk).toBe(9));
    expect(probe()).toBe('7');
  });
});

describe('route context after leaving an org page', () => {
  it('a profile route shows the global name', async () => {
    useUserCacheStore
      .getState()
      .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      });
    const router = createMemoryRouter(
      [
        {
          path: '/tournament/:pk',
          element: (
            <TournamentDisplayOrg tournament={{ organization_pk: 7 }}>
              <Probe />
            </TournamentDisplayOrg>
          ),
        },
        {
          path: '/user/:pk',
          element: (
            <SharedPopoverProvider>
              <Probe />
              <UserStrip user={dragon as never} />
            </SharedPopoverProvider>
          ),
        },
      ],
      { initialEntries: ['/tournament/1'] },
    );
    render(<RouterProvider router={router} />);
    expect(probe()).toBe('7');

    await act(() => router.navigate('/user/1'));

    expect(probe()).toBe('null');
    expect(screen.getAllByText('GwaihirTheWindlord').length).toBeGreaterThan(0);
    expect(screen.queryByText('DragonClaw')).toBeNull();
  });
});

describe('OrgParamDisplayOrg', () => {
  it('provides the organization from the route param', () => {
    render(
      <MemoryRouter initialEntries={['/organizations/7']}>
        <Routes>
          <Route
            path="/organizations/:organizationId"
            element={
              <OrgParamDisplayOrg>
                <Probe />
              </OrgParamDisplayOrg>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(probe()).toBe('7');
  });
});

describe('LeagueDisplayOrg', () => {
  it('uses the nested organization pk', () => {
    render(
      <LeagueDisplayOrg league={{ organization: { pk: 7 } }}>
        <Probe />
      </LeagueDisplayOrg>,
    );
    expect(probe()).toBe('7');
  });

  it('falls back to organization_id', () => {
    render(
      <LeagueDisplayOrg league={{ organization: null, organization_id: 7 }}>
        <Probe />
      </LeagueDisplayOrg>,
    );
    expect(probe()).toBe('7');
  });
});

describe('HeroDraftDisplayOrg', () => {
  it("provides the loaded draft's organization_pk", () => {
    useHeroDraftStore.setState({
      draft: { id: 3, organization_pk: 7 } as never,
    });
    render(
      <HeroDraftDisplayOrg draftId={3}>
        <Probe />
      </HeroDraftDisplayOrg>,
    );
    expect(probe()).toBe('7');
  });

  it('ignores a stale draft for another id', () => {
    useHeroDraftStore.setState({
      draft: { id: 3, organization_pk: 7 } as never,
    });
    render(
      <HeroDraftDisplayOrg draftId={4}>
        <Probe />
      </HeroDraftDisplayOrg>,
    );
    expect(probe()).toBe('null');
  });
});

describe('CurrentTournamentDisplayOrg', () => {
  it("provides the loaded tournament's organization", () => {
    useUserStore
      .getState()
      .setTournament({ pk: 2, organization_pk: 7 } as never);
    render(
      <CurrentTournamentDisplayOrg>
        <Probe />
      </CurrentTournamentDisplayOrg>,
    );
    expect(probe()).toBe('7');
  });
});

describe('EventDisplayOrgLayout', () => {
  it.each(['/events/5', '/events/5/signups', '/rollcall/5'])(
    '%s gets the event organization',
    (path) => {
      const router = createMemoryRouter(
        [
          {
            element: <EventDisplayOrgLayout />,
            children: [
              { path: '/events/:eventId/:tab?', element: <Probe /> },
              { path: '/rollcall/:eventId', element: <Probe /> },
            ],
          },
        ],
        { initialEntries: [path] },
      );
      render(<RouterProvider router={router} />);
      expect(probe()).toBe('7');
    },
  );

  it('is global until the event loads', () => {
    const router = createMemoryRouter(
      [
        {
          element: <EventDisplayOrgLayout />,
          children: [{ path: '/events/:eventId', element: <Probe /> }],
        },
      ],
      { initialEntries: ['/events/6'] },
    );
    render(<RouterProvider router={router} />);
    expect(probe()).toBe('null');
  });
});
