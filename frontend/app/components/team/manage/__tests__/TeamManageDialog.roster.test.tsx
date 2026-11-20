// @vitest-environment jsdom
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { CAPTAIN_CHANGE_WARNING } from '../teamActionCopy';
import { historyPage, managedTeam } from './fixtures';
import {
  axiosError,
  invalidatedKeys,
  openTab,
  renderDialog,
  requestRowAction,
  routeGets,
  stubRadix,
  TEAM_ID,
  TOURNAMENT_PK,
  typeReasonAndConfirm,
} from './manageDialogHarness';

const axiosMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: axiosMock }));

const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMock }));

const logger = vi.hoisted(() => ({
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}));
vi.mock('~/lib/logger', () => ({ getLogger: () => logger }));

const REASON = 'Captain asked to step down';

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  axiosMock.post.mockReset();
  useUserStore.setState({
    currentUser: { pk: 50, username: 'viewer' } as UserType,
  });
  routeGets(axiosMock, { team: managedTeam, org: { pk: 7, admin_ids: [] } });
});

function expectReasonNeverLogged() {
  const logged = JSON.stringify(
    Object.values(logger).map((spy) => spy.mock.calls),
  );
  expect(logged).not.toContain(REASON);
}

async function makeCaptain() {
  await requestRowAction('team-member-row-4', 'Make captain');
  await typeReasonAndConfirm(REASON);
}

describe('TeamManageDialog roster actions', () => {
  it('logs opening and renders the roster', async () => {
    renderDialog();
    expect(await screen.findByTestId('team-member-row-4')).toBeTruthy();
    expect(screen.getByTestId('team-manage-dialog')).toBeTruthy();
    expect(screen.getByTestId('team-manage-tab-roster')).toBeTruthy();
    expect(screen.getByTestId('team-manage-tab-history')).toBeTruthy();
    expect(logger.debug).toHaveBeenCalledWith('Team manage opened', {
      teamId: TEAM_ID,
    });
  });

  it('posts the action, logs success and invalidates the tournament', async () => {
    axiosMock.post.mockResolvedValueOnce({ data: managedTeam });
    const { invalidate } = renderDialog();
    await makeCaptain();
    await waitFor(() =>
      expect(logger.info).toHaveBeenCalledWith('Team action succeeded', {
        teamId: TEAM_ID,
        kind: 'set_captain',
      }),
    );
    expect(axiosMock.post).toHaveBeenCalledWith(
      `/teams/${TEAM_ID}/set-captain/`,
      { reason: REASON, acknowledged_codes: [], user_id: 4 },
    );
    expect(invalidatedKeys(invalidate)).toContainEqual([
      'tournament',
      TOURNAMENT_PK,
    ]);
    expect(toastMock.error).not.toHaveBeenCalled();
    expectReasonNeverLogged();
  });

  it('shows a service refusal inline and in a toast, and logs it at warn', async () => {
    const detail = 'That player is not a member of this team.';
    axiosMock.post.mockRejectedValueOnce(
      axiosError(400, { code: 'not_member', detail }),
    );
    renderDialog();
    await makeCaptain();
    expect(await screen.findByTestId('team-manage-error')).toHaveTextContent(
      detail,
    );
    expect(toastMock.error).toHaveBeenCalledWith(detail);
    expect(logger.warn).toHaveBeenCalledWith('Team action refused', {
      teamId: TEAM_ID,
      kind: 'set_captain',
      code: 'not_member',
    });
    expect(logger.error).not.toHaveBeenCalled();
    expectReasonNeverLogged();
  });

  it('shows a 400 reason error from the server', async () => {
    axiosMock.post.mockRejectedValueOnce(
      axiosError(400, { reason: ['Too short'] }),
    );
    renderDialog();
    await makeCaptain();
    expect(await screen.findByTestId('team-manage-error')).toHaveTextContent(
      'Too short',
    );
    expect(toastMock.error).toHaveBeenCalledWith('Too short');
    expect(logger.error).not.toHaveBeenCalled();
    expectReasonNeverLogged();
  });

  it('on 403 says permission was lost and refetches the managed team', async () => {
    axiosMock.post.mockRejectedValueOnce(
      axiosError(403, { detail: 'not_permitted' }),
    );
    const { invalidate } = renderDialog();
    await makeCaptain();
    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        'You no longer have permission to manage this team',
      ),
    );
    expect(invalidatedKeys(invalidate)).toContainEqual([
      'team',
      TEAM_ID,
      'managed',
    ]);
    expect(logger.warn).toHaveBeenCalledWith('Team action refused', {
      teamId: TEAM_ID,
      kind: 'set_captain',
      code: 'not_permitted',
    });
    expectReasonNeverLogged();
  });

  it('on 500 shows a generic toast and logs the failure at error', async () => {
    axiosMock.post.mockRejectedValueOnce(axiosError(500, 'boom'));
    renderDialog();
    await makeCaptain();
    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith(
        'Something went wrong. Try again.',
      ),
    );
    expect(logger.error).toHaveBeenCalledWith('Team action failed', {
      teamId: TEAM_ID,
      kind: 'set_captain',
      status: 500,
    });
    expectReasonNeverLogged();
  });

  it('on a 404 action closes, reports the team gone and invalidates the tournament', async () => {
    axiosMock.post.mockRejectedValueOnce(axiosError(404, {}));
    const { invalidate, onOpenChange, onTeamGone } = renderDialog();
    await makeCaptain();
    await waitFor(() => expect(onTeamGone).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toastMock.error).toHaveBeenCalledWith('This team no longer exists');
    expect(invalidatedKeys(invalidate)).toContainEqual([
      'tournament',
      TOURNAMENT_PK,
    ]);
    expect(logger.warn).toHaveBeenCalledWith('Team action refused', {
      teamId: TEAM_ID,
      kind: 'set_captain',
      code: 'not_found',
    });
    expect(logger.error).not.toHaveBeenCalled();
    expectReasonNeverLogged();
  });

  it('treats a 404 on the managed team GET as the team being gone', async () => {
    routeGets(axiosMock, { team: axiosError(404, {}) });
    const { invalidate, onOpenChange, onTeamGone } = renderDialog();
    await waitFor(() => expect(onTeamGone).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toastMock.error).toHaveBeenCalledWith('This team no longer exists');
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    expect(invalidatedKeys(invalidate)).toContainEqual([
      'tournament',
      TOURNAMENT_PK,
    ]);
    expect(logger.warn).toHaveBeenCalledWith('Team action refused', {
      teamId: TEAM_ID,
      kind: undefined,
      code: 'not_found',
    });
  });

  it('sub-in with a replacing pick posts replacing_id', async () => {
    axiosMock.post.mockResolvedValueOnce({ data: managedTeam });
    renderDialog();
    await requestRowAction('team-standin-row-12', 'Sub in');
    fireEvent.pointerDown(screen.getByTestId('team-action-replacing'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    fireEvent.click(
      within(screen.getByRole('listbox')).getByRole('option', {
        name: 'roster_m1',
      }),
    );
    await typeReasonAndConfirm(REASON);
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(1));
    expect(axiosMock.post).toHaveBeenCalledWith(`/teams/${TEAM_ID}/sub-in/`, {
      reason: REASON,
      acknowledged_codes: [],
      standin_id: 12,
      replacing_id: 4,
    });
  });

  it('sends one POST for two synchronous confirm clicks', async () => {
    let resolve: (value: unknown) => void = () => undefined;
    axiosMock.post.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderDialog();
    await requestRowAction('team-member-row-4', 'Make captain');
    fireEvent.change(screen.getByTestId('team-action-reason'), {
      target: { value: REASON },
    });
    const confirm = screen.getByTestId('team-action-confirm');
    await waitFor(() => expect(confirm).not.toBeDisabled());
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(1));
    resolve({ data: managedTeam });
    await waitFor(() =>
      expect(logger.info).toHaveBeenCalledWith(
        'Team action succeeded',
        expect.anything(),
      ),
    );
    expect(axiosMock.post).toHaveBeenCalledTimes(1);
  });

  it('warns that the draft resets when a stand-in replaces the captain', async () => {
    renderDialog();
    await requestRowAction('team-standin-row-12', 'Sub in');
    expect(screen.queryByTestId('team-action-warning')).toBeNull();
    fireEvent.pointerDown(screen.getByTestId('team-action-replacing'), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    fireEvent.click(
      within(screen.getByRole('listbox')).getByRole('option', {
        name: 'roster_c (captain)',
      }),
    );
    expect(screen.getByTestId('team-action-warning')).toHaveTextContent(
      CAPTAIN_CHANGE_WARNING,
    );
  });

  it('prefills the last reason when the same action is reopened after a refusal', async () => {
    axiosMock.post.mockRejectedValueOnce(
      axiosError(400, { code: 'not_member', detail: 'No.' }),
    );
    renderDialog();
    await makeCaptain();
    await screen.findByTestId('team-manage-error');
    await waitFor(() =>
      expect(screen.queryByTestId('team-action-dialog')).toBeNull(),
    );
    await requestRowAction('team-member-row-4', 'Make captain');
    expect(screen.getByTestId('team-action-reason')).toHaveValue(REASON);
  });

  it('starts a different action with an empty reason', async () => {
    axiosMock.post.mockRejectedValueOnce(
      axiosError(400, { code: 'not_member', detail: 'No.' }),
    );
    renderDialog();
    await makeCaptain();
    await screen.findByTestId('team-manage-error');
    await waitFor(() =>
      expect(screen.queryByTestId('team-action-dialog')).toBeNull(),
    );
    await requestRowAction('team-dropout-row-5', 'Restore');
    expect(screen.getByTestId('team-action-reason')).toHaveValue('');
  });
});

describe('TeamManageDialog history tab', () => {
  const historyCalls = () =>
    axiosMock.get.mock.calls.filter(
      ([url]) => url === `/teams/${TEAM_ID}/history/`,
    );

  it('does not fetch history until the tab opens, then lists the rows', async () => {
    routeGets(axiosMock, { team: managedTeam, history: historyPage });
    renderDialog();
    await screen.findByTestId('team-member-row-4');
    expect(historyCalls()).toHaveLength(0);
    openTab('team-manage-tab-history');
    const rows = await screen.findAllByTestId('team-history-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('Added stand-in')).toBeTruthy();
    expect(historyCalls()[0][1]).toEqual({
      params: { page: 1, page_size: 25 },
    });
  });

  it('keeps the history scroller inside a single shrinkable grid column', async () => {
    routeGets(axiosMock, { team: managedTeam, history: historyPage });
    renderDialog();
    const dialog = screen.getByTestId('team-manage-dialog');
    expect(dialog).toHaveClass('grid-cols-1');
    openTab('team-manage-tab-history');
    await screen.findAllByTestId('team-history-row');
    expect(within(dialog).getByRole('tablist').parentElement).toHaveClass(
      'min-w-0',
    );
    const scroll = within(dialog).getByTestId('team-history-scroll');
    expect(scroll).toHaveAttribute('role', 'region');
    expect(scroll).toHaveAttribute('aria-label', 'Team history');
  });

  it('requests the next server page from the pager', async () => {
    routeGets(axiosMock, {
      team: managedTeam,
      history: { ...historyPage, count: 30, next: '/next' },
    });
    renderDialog();
    openTab('team-manage-tab-history');
    const next = await screen.findByTestId('team-history-next');
    await waitFor(() => expect(next).not.toBeDisabled());
    fireEvent.click(next);
    await waitFor(() =>
      expect(historyCalls().map(([, cfg]) => cfg.params.page)).toContain(2),
    );
  });

  it('treats a 404 on the history GET as the team being gone', async () => {
    routeGets(axiosMock, { team: managedTeam, history: axiosError(404, {}) });
    const { invalidate, onOpenChange, onTeamGone } = renderDialog();
    await screen.findByTestId('team-member-row-4');
    openTab('team-manage-tab-history');
    await waitFor(() => expect(onTeamGone).toHaveBeenCalledTimes(1));
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(toastMock.error).toHaveBeenCalledWith('This team no longer exists');
    expect(toastMock.error).toHaveBeenCalledTimes(1);
    expect(invalidatedKeys(invalidate)).toContainEqual([
      'tournament',
      TOURNAMENT_PK,
    ]);
    expect(logger.warn).toHaveBeenCalledWith('Team action refused', {
      teamId: TEAM_ID,
      kind: undefined,
      code: 'not_found',
    });
  });

  it('shows an error line when history fails for another reason', async () => {
    routeGets(axiosMock, { team: managedTeam, history: axiosError(500, {}) });
    const { onTeamGone } = renderDialog();
    openTab('team-manage-tab-history');
    expect(
      await screen.findByText('Team history could not be loaded. Try again.'),
    ).toBeTruthy();
    expect(onTeamGone).not.toHaveBeenCalled();
  });
});
