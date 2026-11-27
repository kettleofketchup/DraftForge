// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { DiscordLogSection } from '../DiscordLogSection';

const { get, post, history } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  history: vi.fn(),
}));
vi.mock('~/components/api/axios', () => ({ default: { get, post } }));
vi.mock('~/components/api/api', () => ({
  getEventDiscordState: history,
  fetchCurrentUser: vi.fn(async () => ({})),
}));
vi.mock('../DiscordLogDetailModal', () => ({
  DiscordLogDetailModal: () => null,
}));
const clients: QueryClient[] = [];
const checks = () => ({
  guild_id: '123456789012345678',
  checks: [
    {
      ...fixture.checks[1],
      key: 'attendance_reminder',
      action: 'attendance_reminder',
      status: 'missing_permissions',
      missing: ['EMBED_LINKS'],
      destination: {
        ...fixture.checks[1].destination,
        kind: 'channel',
        name: 'new',
        source: 'configured',
      },
      expires_at: new Date(Date.now() + 60000).toISOString(),
    },
    {
      ...fixture.checks[1],
      key: 'signup_edit',
      action: 'signup_edit',
      status: 'missing_permissions',
      missing: ['VIEW_CHANNEL'],
      destination: {
        ...fixture.checks[1].destination,
        kind: 'channel',
        name: 'old',
        source: 'posted',
      },
      expires_at: new Date(Date.now() + 60000).toISOString(),
    },
  ],
});
function mount(canCheckPermissions = true) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <DiscordLogSection
        eventId={9}
        guildId="123456789012345678"
        canCheckPermissions={canCheckPermissions}
        isAdmin
      />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.resetAllMocks();
  useUserStore.setState({ currentUser: { pk: 1 } as UserType });
  history.mockResolvedValue(null);
  get.mockImplementation(async (path: string) => ({
    data: path.endsWith('permission-checks/')
      ? checks()
      : [
          {
            task: 'confirm_attendance',
            label: 'Confirm attendance',
            status: 'ready',
            can_fire: true,
          },
        ],
  }));
});
afterEach(() => {
  cleanup();
  clients.forEach((c) => c.clear());
  clients.length = 0;
});
it('no history still shows permissions, task diagnostics and a non-submitting batch recheck', async () => {
  mount();
  expect(await screen.findByText('No Discord activity yet')).toBeTruthy();
  expect(
    await screen.findByTestId('discord-permission-badge-attendance_reminder'),
  ).toHaveTextContent('Missing permissions');
  expect(
    await screen.findByTestId(
      'task-permission-confirm_attendance-attendance_reminder',
    ),
  ).toHaveTextContent('Missing permissions');
  fireEvent.click(screen.getByTestId('discord-permission-recheck'));
  await waitFor(() =>
    expect(get).toHaveBeenCalledWith(
      '/events/9/permission-checks/',
      expect.objectContaining({ params: { refresh: true } }),
    ),
  );
  expect(post).not.toHaveBeenCalled();
});
it('history errors show retry independently of permission results', async () => {
  history.mockRejectedValue(new Error('server failed'));
  mount();
  expect(
    await screen.findByText('Unable to load Discord activity'),
  ).toBeTruthy();
  expect(screen.queryByText(/No Discord integration configured/)).toBeNull();
  expect(
    await screen.findByTestId('discord-permission-badge-attendance_reminder'),
  ).toHaveTextContent('Missing permissions');
  history.mockResolvedValue(null);
  fireEvent.click(screen.getByTestId('discord-history-retry'));
  expect(await screen.findByText('No Discord activity yet')).toBeTruthy();
});
it('permission errors do not hide historical posts and historical Posted is neutral', async () => {
  history.mockResolvedValue({
    guild_id: '123456789012345678',
    signup_message: {
      has_posted: true,
      channel_type: 'forum',
      channel_id: '123456789012345679',
      message_id: '123456789012345680',
    },
    announcement: null,
    scheduled_event_id: null,
    dms: [],
    logs: [],
  });
  get.mockImplementation(async (path: string) => {
    if (path.endsWith('permission-checks/')) throw new Error('unavailable');
    return { data: [] };
  });
  mount();
  const posted = await screen.findByText('Posted');
  expect(posted.className).not.toContain('success');
  expect(
    await screen.findByText('Unable to load permission checks'),
  ).toBeTruthy();
});
it('labels posted and next destinations separately while current edit is denied', async () => {
  history.mockResolvedValue({
    guild_id: '123456789012345678',
    signup_message: { has_posted: true, channel_type: 'forum' },
    announcement: null,
    scheduled_event_id: null,
    dms: [],
    logs: [],
  });
  mount();
  expect(await screen.findByText('Posted in #old')).toBeTruthy();
  expect(await screen.findByText('Next post in #new')).toBeTruthy();
  expect(
    screen.getByTestId('discord-permission-badge-signup_edit'),
  ).toHaveTextContent('Missing permissions');
});
it('does not request permission details without explicit staff scope', async () => {
  mount(false);
  expect(await screen.findByText('No Discord activity yet')).toBeTruthy();
  expect(
    get.mock.calls.some(([path]) => path.includes('permission-checks')),
  ).toBe(false);
});
