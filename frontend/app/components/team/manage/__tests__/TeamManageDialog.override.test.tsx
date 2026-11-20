// @vitest-environment jsdom
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import type { OverrideRequired } from '~/components/api/overridesAPI';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { managedTeam } from './fixtures';
import {
  axiosError,
  invalidatedKeys,
  ORG_PK,
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

const VIEWER = 50;
const REASON = 'Cap is fine for this event';
const CAPTAIN_PATH = `/teams/${TEAM_ID}/set-captain/`;

const violation = {
  code: 'team_standin_cap',
  rule: 'override-warning',
  category: 'team' as const,
  message: 'Stand-in cap 2 reached',
  blocking: false,
  params: {},
};
const confirmable: OverrideRequired = {
  code: 'override_required',
  blocked: false,
  violations: [violation],
};
const blocked: OverrideRequired = {
  code: 'override_required',
  blocked: true,
  violations: [{ ...violation, blocking: true }],
};

const org = (adminIds: number[]) => ({
  pk: ORG_PK,
  name: 'Org',
  owner_id: 1,
  admin_ids: adminIds,
  staff_ids: [VIEWER],
});

beforeAll(stubRadix);

beforeEach(() => {
  vi.clearAllMocks();
  axiosMock.post.mockReset();
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  routeGets(axiosMock, { team: managedTeam, org: org([]) });
});

async function startCaptainChange(reason = REASON) {
  await requestRowAction('team-member-row-4', 'Make captain');
  await typeReasonAndConfirm(reason);
}

function expectReasonNeverLogged(...reasons: string[]) {
  const logged = JSON.stringify(
    Object.values(logger).map((spy) => spy.mock.calls),
  );
  for (const reason of reasons) expect(logged).not.toContain(reason);
}

describe('TeamManageDialog overrides', () => {
  it('retries a confirmed override with the acknowledged codes and the reason', async () => {
    axiosMock.post
      .mockRejectedValueOnce(axiosError(409, confirmable))
      .mockResolvedValueOnce({ data: managedTeam });
    const { invalidate } = renderDialog();

    await startCaptainChange();
    const dialog = await screen.findByTestId('override-warning-dialog');
    expect(dialog).toHaveTextContent('Team rule');
    expect(dialog).toHaveTextContent('Stand-in cap 2 reached');
    expect(screen.getByLabelText('Reason (recorded in team history)')).toBe(
      screen.getByTestId('override-reason'),
    );
    expect(screen.getByTestId('override-reason')).toHaveValue(REASON);

    fireEvent.click(screen.getByTestId('override-confirm'));
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(2));
    expect(axiosMock.post.mock.calls[0]).toEqual([
      CAPTAIN_PATH,
      { reason: REASON, acknowledged_codes: [], user_id: 4 },
    ]);
    expect(axiosMock.post.mock.calls[1]).toEqual([
      CAPTAIN_PATH,
      { reason: REASON, acknowledged_codes: ['team_standin_cap'], user_id: 4 },
    ]);
    await waitFor(() =>
      expect(invalidatedKeys(invalidate)).toContainEqual([
        'tournament',
        TOURNAMENT_PK,
      ]),
    );
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(logger.error).not.toHaveBeenCalled();
    expectReasonNeverLogged(REASON);
  });

  it('sends the edited override reason as the recorded reason', async () => {
    axiosMock.post
      .mockRejectedValueOnce(axiosError(409, confirmable))
      .mockResolvedValueOnce({ data: managedTeam });
    renderDialog();
    await startCaptainChange();
    await screen.findByTestId('override-warning-dialog');
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: 'Approved by the org' },
    });
    fireEvent.click(screen.getByTestId('override-confirm'));
    await waitFor(() => expect(axiosMock.post).toHaveBeenCalledTimes(2));
    expect(axiosMock.post.mock.calls[1][1]).toMatchObject({
      reason: 'Approved by the org',
      acknowledged_codes: ['team_standin_cap'],
    });
    expectReasonNeverLogged(REASON, 'Approved by the org');
  });

  it('shows no confirm on a blocked override, and org admins get the settings link', async () => {
    routeGets(axiosMock, { team: managedTeam, org: org([VIEWER]) });
    axiosMock.post.mockRejectedValueOnce(axiosError(409, blocked));
    renderDialog();
    await startCaptainChange();
    await screen.findByTestId('override-warning-dialog');
    expect(screen.queryByTestId('override-confirm')).toBeNull();
    expect(await screen.findByTestId('override-settings-link')).toBeTruthy();
    expect(axiosMock.get).toHaveBeenCalledWith(`/organizations/${ORG_PK}/`);
  });

  it('shows no settings link to staff who are not org admins', async () => {
    axiosMock.post.mockRejectedValueOnce(axiosError(409, blocked));
    renderDialog();
    await startCaptainChange();
    await screen.findByTestId('override-warning-dialog');
    expect(screen.queryByTestId('override-confirm')).toBeNull();
    expect(screen.queryByTestId('override-settings-link')).toBeNull();
  });

  it('maps a retry override_reason_required to the reason error', async () => {
    axiosMock.post
      .mockRejectedValueOnce(axiosError(409, confirmable))
      .mockRejectedValueOnce(
        axiosError(400, { code: 'override_reason_required' }),
      );
    renderDialog();
    await startCaptainChange();
    await screen.findByTestId('override-warning-dialog');
    fireEvent.click(screen.getByTestId('override-confirm'));
    expect(await screen.findByTestId('override-reason-error')).toBeTruthy();
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('rejects a one-character override reason without retrying', async () => {
    axiosMock.post.mockRejectedValueOnce(axiosError(409, confirmable));
    renderDialog();
    await startCaptainChange();
    await screen.findByTestId('override-warning-dialog');
    fireEvent.change(screen.getByTestId('override-reason'), {
      target: { value: 'x' },
    });
    fireEvent.click(screen.getByTestId('override-confirm'));
    expect(
      await screen.findByText('Give a reason (at least 3 characters).'),
    ).toBeTruthy();
    expect(axiosMock.post).toHaveBeenCalledTimes(1);
  });

  it('prefills the override reason with the action reason on each open', async () => {
    axiosMock.post
      .mockRejectedValueOnce(axiosError(409, confirmable))
      .mockRejectedValueOnce(axiosError(409, confirmable));
    renderDialog();

    await startCaptainChange('First reason here');
    await screen.findByTestId('override-warning-dialog');
    expect(screen.getByTestId('override-reason')).toHaveValue(
      'First reason here',
    );
    fireEvent.keyDown(screen.getByTestId('override-warning-dialog'), {
      key: 'Escape',
    });
    await waitFor(() =>
      expect(screen.queryByTestId('override-warning-dialog')).toBeNull(),
    );

    await startCaptainChange('Second reason here');
    await screen.findByTestId('override-warning-dialog');
    expect(screen.getByTestId('override-reason')).toHaveValue(
      'Second reason here',
    );
    expectReasonNeverLogged('First reason here', 'Second reason here');
  });
});
