// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { CreateSeriesEventModal } from '../CreateSeriesEventModal';
import { openTab, orgDefaults, repeater, Wrapper } from './eventModalFixtures';

const mocks = vi.hoisted(() => ({ post: vi.fn(), create: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { post: mocks.post } }));
vi.mock('~/components/api/api', async (original) => ({
  ...(await original<typeof import('~/components/api/api')>()),
  createSeriesOneOffEvent: mocks.create,
  getOrgEventDefaults: vi.fn(async () => ({
    ...orgDefaults,
    discord_confirm_attendance: true,
    discord_profile_reminder: true,
    discord_confirm_attendance_channel_id: '900000000000000008',
    discord_profile_reminder_channel_id: '900000000000000009',
  })),
  fetchOrganization: vi.fn(async () => ({
    pk: 1,
    discord_server_id: '900000000000000001',
    staff_ids: [1],
  })),
  getDiscordRoles: vi.fn(async () => []),
  getDiscordChannels: vi.fn(async () => []),
  getLeagues: vi.fn(async () => []),
}));
vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));
vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: (p: {
    value: string;
    onChange: (v: string) => void;
    'data-testid': string;
  }) => (
    <input
      data-testid={p['data-testid']}
      value={p.value || ''}
      onChange={(e) => p.onChange(e.target.value)}
    />
  ),
}));
vi.mock('../DiscordRolePicker', () => ({ DiscordRolePicker: () => null }));

beforeEach(() => {
  useUserStore.setState({ currentUser: { pk: 1 } as UserType });
  mocks.post.mockReset();
  mocks.create.mockReset();
});
afterEach(cleanup);
it('previews changed unsaved destinations through organization scope, ignoring an old response', async () => {
  let resolveOld!: (v: unknown) => void;
  const response = (body: {
    checks: { key: string; action: string; channel_id: string | null }[];
  }) => ({
    data: {
      guild_id: '900000000000000001',
      checks: body.checks.map((d) => ({
        ...fixture.checks[0],
        ...d,
        status: 'verified',
        destination: {
          ...fixture.checks[0].destination,
          channel_id: d.channel_id,
        },
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      })),
    },
  });
  mocks.post
    .mockImplementationOnce(
      (_path, body) =>
        new Promise((resolve) => {
          resolveOld = () => resolve(response(body));
        }),
    )
    .mockImplementation(async (_path, body) => response(body));
  render(
    <CreateSeriesEventModal
      open
      onOpenChange={() => {}}
      repeater={{
        ...repeater,
        discord_confirm_attendance: true,
        discord_confirm_attendance_channel_id: '900000000000000008',
      }}
    />,
    { wrapper: Wrapper },
  );
  openTab(/Discord/);
  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(1));
  fireEvent.change(
    screen.getByTestId('discord-confirm-attendance-channel-select'),
    { target: { value: '900000000000000010' } },
  );
  expect(
    screen.getByTestId('discord-permission-badge-attendance_reminder'),
  ).not.toHaveTextContent('Permissions verified');
  resolveOld(undefined);
  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
  expect(mocks.post.mock.calls[1][0]).toBe(
    '/discord/organizations/1/permission-checks/',
  );
  expect(mocks.post.mock.calls[1][1].checks).toContainEqual(
    expect.objectContaining({
      key: 'attendance_reminder',
      channel_id: '900000000000000010',
    }),
  );
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-attendance_reminder'),
    ).toHaveTextContent('Permissions verified'),
  );
  expect(
    mocks.post.mock.calls.every(([path]) => !path.startsWith('/events/')),
  ).toBe(true);
  expect(mocks.create).not.toHaveBeenCalled();
});
