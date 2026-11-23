// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { searchUsers, type SearchUserResult } from '~/components/api/api';
import { WalkInPicker } from '../WalkInPicker';

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  searchUsers: vi.fn(),
}));

function user(
  pk: number,
  membership: SearchUserResult['membership'],
  extra: Partial<SearchUserResult> = {},
): SearchUserResult {
  return { pk, username: `user${pk}`, membership, ...extra };
}

function renderPicker(excludeUserPks: ReadonlySet<number> = new Set()) {
  const onPick = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WalkInPicker
        open
        onOpenChange={vi.fn()}
        orgId={1}
        excludeUserPks={excludeUserPks}
        onPick={onPick}
      />
    </QueryClientProvider>,
  );
  return { onPick, client };
}

function type(value: string) {
  fireEvent.change(screen.getByTestId('attendance-walkin-search'), {
    target: { value },
  });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('WalkInPicker', () => {
  it('does not search under 2 characters', async () => {
    vi.mocked(searchUsers).mockResolvedValue([]);
    renderPicker();

    type('a');
    expect(
      await screen.findByTestId('attendance-walkin-hint'),
    ).toHaveTextContent('Type at least 2 characters');
    type(' a ');
    await new Promise((r) => setTimeout(r, 400));
    expect(searchUsers).not.toHaveBeenCalled();
    expect(screen.getByTestId('attendance-walkin-hint')).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-walkin-empty')).toBeNull();

    type('abc');
    await waitFor(() => expect(searchUsers).toHaveBeenCalledTimes(1));
    expect(searchUsers).toHaveBeenCalledWith('abc', 1, undefined);
    expect(screen.queryByTestId('attendance-walkin-hint')).toBeNull();
  });

  it('offers only org members not already listed', async () => {
    vi.mocked(searchUsers).mockResolvedValue([
      user(5, 'org'),
      user(6, 'other_org'),
      user(7, 'league'),
      user(8, 'org'),
      { username: 'nopk', membership: 'org' },
    ]);
    renderPicker(new Set([8]));
    type('user');

    expect(
      await screen.findByTestId('attendance-walkin-option-5'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-walkin-option-6')).toBeNull();
    expect(screen.queryByTestId('attendance-walkin-option-7')).toBeNull();
    expect(screen.queryByTestId('attendance-walkin-option-8')).toBeNull();
    expect(screen.getAllByTestId(/^attendance-walkin-option-/)).toHaveLength(1);
  });

  it('picking calls onPick with a WalkIn', async () => {
    vi.mocked(searchUsers).mockResolvedValue([
      user(5, 'org', {
        nickname: 'Fives',
        avatarUrl: 'https://cdn.example.com/a.png',
      }),
      user(9, 'org', { username: null }),
    ]);
    const { onPick } = renderPicker();
    type('fiv');

    fireEvent.click(await screen.findByTestId('attendance-walkin-option-5'));
    expect(onPick).toHaveBeenCalledWith({
      user_pk: 5,
      username: 'user5',
      nickname: 'Fives',
      avatarUrl: 'https://cdn.example.com/a.png',
    });

    fireEvent.click(screen.getByTestId('attendance-walkin-option-9'));
    expect(onPick).toHaveBeenLastCalledWith({
      user_pk: 9,
      username: '',
      nickname: null,
      avatarUrl: null,
    });
  });

  it('shows the empty note when nothing matches', async () => {
    vi.mocked(searchUsers).mockResolvedValue([user(6, 'other_org')]);
    renderPicker();
    type('zzz');

    expect(
      await screen.findByTestId('attendance-walkin-empty'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('attendance-walkin-hint')).toBeNull();
  });

  it('shows the API error', async () => {
    vi.mocked(searchUsers).mockRejectedValue(
      Object.assign(new Error('Request failed'), {
        isAxiosError: true,
        response: { status: 403, data: { detail: 'Org staff only' } },
      }),
    );
    renderPicker();
    type('abc');

    expect(
      await screen.findByTestId('attendance-walkin-error'),
    ).toHaveTextContent('Org staff only');
  });
});
