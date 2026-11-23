// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { AddStandinPicker } from '../AddStandinPicker';
import { managedTeam } from './fixtures';
import {
  axiosError,
  ORG_PK,
  renderDialog,
  routeGets,
  stubRadix,
  TEAM_ID,
  typeReasonAndConfirm,
} from './manageDialogHarness';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));

const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));

vi.mock('~/lib/logger', () => ({
  getLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}));

const VIEWER = 50;
const LEAGUE_PK = 3;

const org = (staffIds: number[]): OrganizationType =>
  ({
    pk: ORG_PK,
    name: 'Org',
    owner_id: 1,
    admin_ids: [],
    staff_ids: staffIds,
  }) as unknown as OrganizationType;

const results = [
  {
    pk: 20,
    username: 'org_player',
    membership: 'org',
    membership_label: 'Org',
  },
  {
    pk: 21,
    username: 'elsewhere',
    membership: 'other_org',
    membership_label: 'Other Org',
  },
  { pk: 22, username: 'nobody', membership: null, membership_label: null },
  { pk: 4, username: 'roster_m1', membership: 'org', membership_label: 'Org' },
];

const searchCalls = () =>
  axiosMock.get.mock.calls.filter(([url]) => url === '/users/search/');

function renderPicker(
  props: Partial<Parameters<typeof AddStandinPicker>[0]> = {},
) {
  const onPick = vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <AddStandinPicker
        organization={org([VIEWER])}
        leaguePk={LEAGUE_PK}
        excludePks={[4]}
        onPick={onPick}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onPick };
}

async function search(text: string) {
  fireEvent.click(screen.getByRole('button', { name: /add stand-in/i }));
  const input = await screen.findByTestId('team-standin-search');
  fireEvent.change(input, { target: { value: text } });
}

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  axiosMock.get.mockReset();
  axiosMock.post.mockReset();
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  axiosMock.get.mockResolvedValue({ data: results });
});

describe('AddStandinPicker', () => {
  it('sends no request under two characters and shows a hint', async () => {
    renderPicker();
    await search('a');
    expect(screen.getByText(/at least 2 characters/i)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 400));
    expect(searchCalls()).toHaveLength(0);
  });

  it('org staff send org_id and see the "Not in this organization" group', async () => {
    renderPicker();
    await search('abc');
    expect(await screen.findByTestId('team-standin-result-20')).toBeTruthy();
    expect(searchCalls()).toHaveLength(1);
    expect(searchCalls()[0][1]).toEqual({
      params: { q: 'abc', org_id: ORG_PK, league_id: LEAGUE_PK },
    });
    const group = screen.getByText('Not in this organization');
    expect(group).toBeTruthy();
    const outside = screen.getByTestId('team-standin-result-21');
    expect(outside).toHaveTextContent('Other Org');
    expect(
      group.compareDocumentPosition(outside) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      screen
        .getByTestId('team-standin-result-20')
        .compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByText(/membership can't be shown/i)).toBeNull();
  });

  it('league staff who are not org staff send no org_id and see the note', async () => {
    renderPicker({ organization: org([]) });
    await search('abc');
    expect(await screen.findByTestId('team-standin-result-20')).toBeTruthy();
    expect(searchCalls()[0][1]).toEqual({ params: { q: 'abc' } });
    expect(
      screen.getByText("Organization membership can't be shown for your role."),
    ).toBeTruthy();
    expect(screen.queryByText('Not in this organization')).toBeNull();
  });

  it('searches everyone with a neutral note when the tournament has no organization', async () => {
    useUserStore.setState({
      currentUser: {
        pk: VIEWER,
        username: 'viewer',
        is_staff: true,
      } as UserType,
    });
    renderPicker({ organization: null });
    await search('abc');
    expect(await screen.findByTestId('team-standin-result-20')).toBeTruthy();
    expect(searchCalls()[0][1]).toEqual({ params: { q: 'abc' } });
    expect(
      screen.getByText('This tournament has no organization to rank by.'),
    ).toBeTruthy();
    expect(screen.queryByText(/for your role/i)).toBeNull();
  });

  it('marks players on another team and does not let them be picked', async () => {
    const { onPick } = renderPicker({ otherTeamPks: [20] });
    await search('abc');
    const row = await screen.findByTestId('team-standin-result-20');
    expect(row).toHaveTextContent('On another team');
    expect(row).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(row);
    expect(onPick).not.toHaveBeenCalled();
  });

  it('shows "Search unavailable" when the search fails', async () => {
    axiosMock.get.mockRejectedValue(axiosError(403, {}));
    renderPicker();
    await search('abc');
    expect(await screen.findByText('Search unavailable')).toBeTruthy();
  });

  it('does not list excluded users', async () => {
    renderPicker();
    await search('abc');
    await screen.findByTestId('team-standin-result-20');
    expect(screen.queryByTestId('team-standin-result-4')).toBeNull();
  });

  it('calls onPick with the chosen user', async () => {
    const { onPick } = renderPicker();
    await search('abc');
    fireEvent.click(await screen.findByTestId('team-standin-result-22'));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0][0]).toMatchObject({
      pk: 22,
      username: 'nobody',
    });
    await waitFor(() =>
      expect(screen.queryByTestId('team-standin-search')).toBeNull(),
    );
  });

  it('is disabled when disabled is set', () => {
    renderPicker({ disabled: true });
    expect(
      screen.getByRole('button', { name: /add stand-in/i }),
    ).toBeDisabled();
  });
});

describe('TeamManageDialog stand-in search', () => {
  const STANDINS_PATH = `/teams/${TEAM_ID}/standins/`;
  const REASON = 'Covering for an absent player';

  beforeEach(() => {
    routeGets(axiosMock, {
      team: managedTeam,
      org: org([VIEWER]),
      search: results,
    });
  });

  async function pickFromDialog(pk: number) {
    await screen.findByTestId('team-standin-row-12');
    await search('abc');
    fireEvent.click(await screen.findByTestId(`team-standin-result-${pk}`));
    await screen.findByTestId('team-action-dialog');
  }

  it('marks players the server reports on other teams', async () => {
    routeGets(axiosMock, {
      team: { ...managedTeam, other_team_user_pks: [21] },
      org: org([VIEWER]),
      search: results,
    });
    renderDialog();
    await screen.findByTestId('team-standin-row-12');
    await search('abc');
    expect(
      await screen.findByTestId('team-standin-result-21'),
    ).toHaveTextContent('On another team');
  });

  it('excludes the team roster and opens the reason dialog for add_standin', async () => {
    axiosMock.post.mockResolvedValueOnce({ data: managedTeam });
    renderDialog();
    await screen.findByTestId('team-standin-row-12');
    await search('abc');
    await screen.findByTestId('team-standin-result-20');
    expect(screen.queryByTestId('team-standin-result-4')).toBeNull();
    await waitFor(() =>
      expect(searchCalls().at(-1)?.[1]).toEqual({
        params: { q: 'abc', org_id: ORG_PK, league_id: 3 },
      }),
    );
    fireEvent.click(screen.getByTestId('team-standin-result-20'));
    const dialog = await screen.findByTestId('team-action-dialog');
    expect(dialog).toHaveTextContent('Add stand-in?');
    expect(dialog).toHaveTextContent('org_player');

    await typeReasonAndConfirm(REASON);
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(1));
    expect(axiosMock.post.mock.calls[0]).toEqual([
      STANDINS_PATH,
      { reason: REASON, acknowledged_codes: [], user_id: 20 },
    ]);
  });

  it('retries a stand-in cap override with team_standin_cap acknowledged', async () => {
    axiosMock.post
      .mockRejectedValueOnce(
        axiosError(409, {
          code: 'override_required',
          blocked: false,
          violations: [
            {
              code: 'team_standin_cap',
              rule: 'override-warning',
              category: 'team',
              message: 'Stand-in cap 2 reached',
              blocking: false,
              params: {},
            },
          ],
        }),
      )
      .mockResolvedValueOnce({ data: managedTeam });
    renderDialog();
    await pickFromDialog(22);
    await typeReasonAndConfirm(REASON);

    const override = await screen.findByTestId('override-warning-dialog');
    expect(override).toHaveTextContent('Stand-in cap 2 reached');
    fireEvent.click(screen.getByTestId('override-confirm'));
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(2));
    expect(axiosMock.post.mock.calls[1]).toEqual([
      STANDINS_PATH,
      {
        reason: REASON,
        acknowledged_codes: ['team_standin_cap'],
        user_id: 22,
      },
    ]);
    expect(toastMock.error).not.toHaveBeenCalled();
  });
});
