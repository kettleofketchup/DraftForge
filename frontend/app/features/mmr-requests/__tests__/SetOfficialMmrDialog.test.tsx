// @vitest-environment jsdom
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '~/components/api/axios';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import type { MmrScope } from '../queryKeys';
import {
  SetOfficialMmrDialog,
  type SetOfficialMember,
} from '../SetOfficialMmrDialog';
import { mmrRequest, mmrSummary } from './fixtures';
import { httpError, installDomStubs, renderWithClient } from './harness';

vi.mock('~/components/api/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const MEMBER: SetOfficialMember = {
  userPk: 42,
  orgUserPk: 117,
  name: 'member',
};

beforeEach(() => {
  installDomStubs();
  useUserStore.setState({ currentUser: { pk: 9 } as UserType });
  vi.mocked(api.get).mockResolvedValue({ data: mmrSummary() });
  vi.mocked(api.post).mockResolvedValue({
    data: mmrRequest({ status: 'approved', source: 'staff' }),
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

function renderDialog(scope: MmrScope = { org: 3 }, member = MEMBER) {
  const onOpenChange = vi.fn();
  renderWithClient(
    <SetOfficialMmrDialog
      scope={scope}
      member={member}
      open
      onOpenChange={onOpenChange}
    />,
  );
  return { onOpenChange };
}

function postedForm(): [string, FormData] {
  const [url, body] = vi.mocked(api.post).mock.calls[0];
  return [url as string, body as FormData];
}

describe('SetOfficialMmrDialog', () => {
  it('lists org games and the member leagues in the org', async () => {
    renderDialog();
    expect(
      await screen.findByTestId('set-official-mmr-target-league-5'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('set-official-mmr-target-org-1'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('set-official-mmr-target-org-2'),
    ).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/users/42/mmrs/');
  });

  it('submits an org game without a screenshot', async () => {
    const { onOpenChange } = renderDialog();
    await screen.findByTestId('set-official-mmr-target-league-5');
    fireEvent.change(screen.getByTestId('set-official-mmr-value'), {
      target: { value: '5000' },
    });
    fireEvent.click(screen.getByTestId('set-official-mmr-submit'));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, form] = postedForm();
    expect(url).toBe('/organizations/3/mmr-requests/staff-set/');
    expect(form).toBeInstanceOf(FormData);
    expect(form.get('target')).toBe('org');
    expect(form.get('org_user')).toBe('117');
    expect(form.get('game_type')).toBe('1');
    expect(form.get('mmr')).toBe('5000');
    expect(form.has('screenshot')).toBe(false);
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('submits a league target with a screenshot and note', async () => {
    renderDialog();
    fireEvent.click(
      await screen.findByTestId('set-official-mmr-target-league-5'),
    );
    fireEvent.change(screen.getByTestId('set-official-mmr-value'), {
      target: { value: '5200' },
    });
    fireEvent.change(screen.getByTestId('mmr-screenshot-input'), {
      target: {
        files: [new File(['png'], 'rank.png', { type: 'image/png' })],
      },
    });
    fireEvent.change(screen.getByTestId('set-official-mmr-note'), {
      target: { value: 'Checked in lobby' },
    });
    fireEvent.click(screen.getByTestId('set-official-mmr-submit'));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [, form] = postedForm();
    expect(form.get('target')).toBe('league');
    expect(form.get('league_user')).toBe('300');
    expect(form.has('game_type')).toBe(false);
    expect(form.get('screenshot')).toBeInstanceOf(File);
    expect(form.get('note')).toBe('Checked in lobby');
  });

  it('offers only the league in league scope', async () => {
    renderDialog({ league: 5 }, { userPk: 42, name: 'member' });
    expect(
      await screen.findByTestId('set-official-mmr-target-league-5'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('set-official-mmr-target-org-1'),
    ).not.toBeInTheDocument();
  });

  it('rejects an out-of-range value', async () => {
    renderDialog();
    await screen.findByTestId('set-official-mmr-target-league-5');
    fireEvent.change(screen.getByTestId('set-official-mmr-value'), {
      target: { value: '0' },
    });
    fireEvent.click(screen.getByTestId('set-official-mmr-submit'));
    expect(
      await screen.findByText('MMR must be at least 1'),
    ).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('explains a self-review refusal', async () => {
    vi.mocked(api.post).mockRejectedValueOnce(
      httpError(403, { error: 'self_review' }),
    );
    renderDialog();
    await screen.findByTestId('set-official-mmr-target-league-5');
    fireEvent.change(screen.getByTestId('set-official-mmr-value'), {
      target: { value: '5000' },
    });
    fireEvent.click(screen.getByTestId('set-official-mmr-submit'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "You can't verify your own MMR. Ask another staff member.",
      ),
    );
  });
});
