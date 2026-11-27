// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import type { ReactNode, RefObject } from 'react';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ProfileButton } from '~/components/navbar/login';
import type { OrganizationType } from '~/components/organization/schemas';
import { useOrgProfileSections } from '~/components/organization/tabs/orgSettings/useOrgProfileSections';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import { getEventPermissionChecks } from '../api';
import { useSavedEventPermissions } from '../queries';
import { discordPermissionKeys } from '../queryKeys';
import type { PermissionChecksResponse } from '../schemas';

const { updateOrganization, logout } = vi.hoisted(() => ({
  updateOrganization: vi.fn(),
  logout: vi.fn(),
}));
vi.mock('~/components/api/api', () => ({
  updateOrganization,
  logout,
  fetchCurrentUser: vi.fn(async () => ({})),
}));
vi.mock('../api', () => ({ getEventPermissionChecks: vi.fn() }));
vi.mock('~/features/discord-connect', () => ({
  DiscordConnectionCard: () => null,
  discordConnectKeys: { botStatus: (id: number) => ['bot-status', id] },
}));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock('~/components/teamdraft/DraftNotificationBadge', () => ({
  DraftNotificationBadge: () => null,
}));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/ui/dropdown-menu', () => {
  const Pass = ({ children }: { children?: ReactNode }) => (
    <div>{children}</div>
  );
  return {
    DropdownMenu: Pass,
    DropdownMenuContent: Pass,
    DropdownMenuItem: Pass,
    DropdownMenuLabel: Pass,
    DropdownMenuSeparator: () => null,
    DropdownMenuTrigger: Pass,
  };
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function response(): PermissionChecksResponse {
  return {
    ...fixture,
    checks: [
      {
        ...fixture.checks[1],
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60000).toISOString(),
      },
    ],
  } as PermissionChecksResponse;
}
let client: QueryClient;
let unit: SettingsFormUnit;
let permissionQuery: ReturnType<typeof useSavedEventPermissions>;
const org = {
  pk: 7,
  name: 'Permission Org',
  description: '',
  logo: '',
  timezone: 'America/New_York',
  discord_server_id: '123456789012345678',
} as OrganizationType;
const sectionsRef = {
  current: null,
} as RefObject<SettingsDialogHandle<string> | null>;
function Harness({
  guildId = org.discord_server_id ?? null,
}: {
  guildId?: string | null;
}) {
  const { sections, unit: profile } = useOrgProfileSections(org, sectionsRef);
  unit = profile;
  permissionQuery = useSavedEventPermissions({
    eventId: 9,
    guildId,
    enabled: true,
  });
  return (
    <>
      <ProfileButton />
      {sections.find((section) => section.value === 'discord')?.content}
    </>
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useUserStore.setState({
    currentUser: { pk: 1, username: 'viewer' } as UserType,
  });
  vi.mocked(getEventPermissionChecks).mockResolvedValue(response());
  updateOrganization.mockResolvedValue(org);
  logout.mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  client.clear();
});
it.each([
  ['server', 'ordinary'],
  ['server', 'manual'],
  ['logout', 'ordinary'],
  ['logout', 'manual'],
] as const)(
  '%s cleanup rejects late %s responses and removes old grants',
  async (identity, kind) => {
    const view = render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Harness />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(permissionQuery.state).toBe('ready'));
    const late = deferred<PermissionChecksResponse>();
    vi.mocked(getEventPermissionChecks).mockReturnValue(late.promise);
    let pending!: Promise<unknown>;
    await act(async () => {
      pending =
        kind === 'manual'
          ? permissionQuery.recheck()
          : permissionQuery.refetch();
    });
    const signal = vi.mocked(getEventPermissionChecks).mock.calls[1][2]!;
    if (identity === 'server') {
      fireEvent.change(screen.getByTestId('org-discord-server-id-input'), {
        target: { value: '223456789012345678' },
      });
      await act(async () => {
        expect(await unit.save()).toBe(true);
      });
    } else {
      await act(async () => {
        fireEvent.click(screen.getByTestId('navbarLogoutButton'));
      });
    }
    expect(signal.aborted).toBe(true);
    const key = discordPermissionKeys.saved(1, 9, org.discord_server_id!);
    expect(client.getQueryData(key)).toBeUndefined();
    const fresh = deferred<PermissionChecksResponse>();
    vi.mocked(getEventPermissionChecks).mockReturnValue(fresh.promise);
    if (identity === 'logout')
      act(() =>
        useUserStore.setState({
          currentUser: { pk: 2, username: 'next-viewer' } as UserType,
        }),
      );
    view.rerender(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <Harness
            guildId={
              identity === 'server'
                ? '223456789012345678'
                : org.discord_server_id
            }
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await act(async () => {
      late.resolve(response());
      await pending;
    });
    expect(client.getQueryData(key)).toBeUndefined();
    expect(permissionQuery.results.size).toBe(0);
    const nextKey = discordPermissionKeys.saved(
      identity === 'logout' ? 2 : 1,
      9,
      identity === 'server' ? '223456789012345678' : org.discord_server_id!,
    );
    expect(client.getQueryData(nextKey)).toBeUndefined();
  },
);
