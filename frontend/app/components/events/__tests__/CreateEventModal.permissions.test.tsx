// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fetchOrganization } from '~/components/api/api';
import type { OrganizationType } from '~/components/organization/schemas';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { CreateEventModal } from '../CreateEventModal';
import { openTab, orgDefaults, Wrapper } from './eventModalFixtures';

const mocks = vi.hoisted(() => ({ post: vi.fn(), create: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { post: mocks.post } }));
vi.mock('~/components/api/api', async (original) => ({
  ...(await original<typeof import('~/components/api/api')>()),
  createEvent: mocks.create,
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
  render(<CreateEventModal open onOpenChange={() => {}} organizationId={1} />, {
    wrapper: Wrapper,
  });
  await screen.findByTestId('event-name-input');
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
it('does not request permission data for an ordinary organization viewer', async () => {
  vi.mocked(fetchOrganization).mockClear();
  useUserStore.setState({ currentUser: { pk: 2 } as UserType });
  render(<CreateEventModal open onOpenChange={() => {}} organizationId={1} />, {
    wrapper: Wrapper,
  });
  await screen.findByTestId('event-name-input');
  openTab(/Discord/);
  await waitFor(() => expect(fetchOrganization).toHaveBeenCalledWith(1));
  expect(
    screen.queryByTestId('discord-permission-badge-attendance_reminder'),
  ).not.toBeInTheDocument();
  expect(mocks.post).not.toHaveBeenCalled();
});
it('drops prior organization grants while the new organization context loads', async () => {
  const org = {
    pk: 1,
    discord_server_id: '900000000000000001',
    staff_ids: [1],
  } as OrganizationType;
  let resolveOrganization!: (org: OrganizationType) => void;
  vi.mocked(fetchOrganization)
    .mockResolvedValueOnce(org)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        resolveOrganization = resolve;
      }),
    );
  mocks.post.mockImplementation(async (_path, body) => ({
    data: {
      guild_id: org.discord_server_id,
      checks: body.checks.map((d: { key: string; action: string }) => ({
        ...fixture.checks[0],
        ...d,
        status: 'verified',
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      })),
    },
  }));
  function SwitchingModal() {
    const [organizationId, setOrganizationId] = useState(1);
    return (
      <>
        <button onClick={() => setOrganizationId(2)}>
          Change organization
        </button>
        <CreateEventModal
          open
          onOpenChange={() => {}}
          organizationId={organizationId}
        />
      </>
    );
  }
  render(<SwitchingModal />, { wrapper: Wrapper });
  await screen.findByTestId('event-name-input');
  openTab(/Discord/);
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-attendance_reminder'),
    ).toHaveTextContent('Permissions verified'),
  );
  fireEvent.click(screen.getByText('Change organization'));
  await waitFor(() => expect(fetchOrganization).toHaveBeenCalledWith(2));
  expect(
    screen.queryByTestId('discord-permission-badge-attendance_reminder'),
  ).not.toBeInTheDocument();
  expect(mocks.post).toHaveBeenCalledTimes(1);
  resolveOrganization({
    ...org,
    pk: 2,
    discord_server_id: '900000000000000002',
  });
  await waitFor(() => expect(mocks.post).toHaveBeenCalledTimes(2));
  expect(mocks.post.mock.calls[1][0]).toBe(
    '/discord/organizations/2/permission-checks/',
  );
});
