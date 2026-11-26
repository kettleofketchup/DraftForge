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
import { useForm, type UseFormReturn } from 'react-hook-form';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Form } from '~/components/ui/form';
import type { PermissionScope } from '~/features/discord-permissions';
import type { UserType } from '~/index';
import { useUserStore } from '~/store/userStore';
import fixture from '../../../../../backend/discordbot/tests/permission_checks_fixture.json';
import {
  DiscordConfigSection,
  type DiscordFields,
} from '../DiscordConfigSection';
import { DISCORD_CONFIG_DEFAULTS } from '../schemas';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('~/components/api/axios', () => ({ default: { post } }));
vi.mock('../DiscordChannelPicker', () => ({
  DiscordChannelPicker: () => null,
}));
vi.mock('../DiscordRolePicker', () => ({ DiscordRolePicker: () => null }));
let form: UseFormReturn<DiscordFields>;
const submit = vi.fn();
const clients: QueryClient[] = [];
function Harness({
  scope = { kind: 'org', orgId: 7, guildId: '900000000000000001' },
  canCheck = true,
  isRepeater = true,
  showSignupReminder,
}: {
  scope?: PermissionScope | null;
  canCheck?: boolean;
  isRepeater?: boolean;
  showSignupReminder?: boolean;
}) {
  form = useForm<DiscordFields>({
    defaultValues: {
      ...DISCORD_CONFIG_DEFAULTS,
      discord_create_event: true,
      discord_post_signups: true,
      discord_announcement: true,
      discord_start_mention: true,
      discord_confirm_attendance: true,
      discord_profile_reminder: true,
      discord_notify_new_events: true,
      discord_announcement_channel_id: '900000000000000003',
    },
  });
  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(submit)}>
        <DiscordConfigSection
          control={form.control}
          organizationId={7}
          isRepeater={isRepeater}
          showSignupReminder={showSignupReminder}
          permissionScope={scope}
          canCheckPermissions={canCheck}
        />
        <button type="submit">Save</button>
      </form>
    </Form>
  );
}
function mount(props: Parameters<typeof Harness>[0] = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <Harness {...props} />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  post.mockReset();
  submit.mockReset();
  useUserStore.setState({ currentUser: { pk: 1 } as UserType });
  post.mockImplementation(async (_path, body) => ({
    data: {
      guild_id: '900000000000000001',
      checks: body.checks.map(
        (d: { key: string; action: string; channel_id: string | null }) => ({
          ...fixture.checks[0],
          ...d,
          status: 'missing_permissions',
          missing: ['EMBED_LINKS'],
          checked_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 60_000).toISOString(),
        }),
      ),
    },
  }));
});
afterEach(() => {
  cleanup();
  clients.forEach((c) => c.clear());
  clients.length = 0;
});
it('batches every visible operation, renders diagnostics and never blocks saving', async () => {
  mount();
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  for (const key of [
    'signup_fallback',
    'announcement',
    'attendance_reminder',
    'profile_reminder',
    'new_event_notice',
    'start_mention',
    'scheduled_event_create',
    'scheduled_event_update',
    'mark_interested',
    'signup_reminder',
  ])
    expect(
      screen.getByTestId(`discord-permission-badge-${key}`),
    ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-scheduled_event_create'),
    ).toHaveTextContent('Missing permissions'),
  );
  fireEvent.click(
    screen.getByTestId('discord-permission-badge-attendance_reminder'),
  );
  expect(submit).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('Save'));
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
});
it('checks and badges the visible reminder in organization defaults', async () => {
  mount({ isRepeater: false, showSignupReminder: true });
  expect(
    screen.getByTestId('discord-discord_signup_reminder'),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-signup_reminder'),
    ).toHaveTextContent('Missing permissions'),
  );
  expect(post.mock.calls[0][1].checks).toContainEqual(
    expect.objectContaining({
      key: 'signup_reminder',
      action: 'signup_reminder_dm',
    }),
  );
});
it.each([
  { isRepeater: false },
  { isRepeater: true, showSignupReminder: false },
])('does not check a hidden reminder: %j', async (props) => {
  mount(props);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(screen.queryByTestId('discord-discord_signup_reminder')).toBeNull();
  expect(
    screen.queryByTestId('discord-permission-badge-signup_reminder'),
  ).toBeNull();
  expect(post.mock.calls[0][1].checks).not.toContainEqual(
    expect.objectContaining({ key: 'signup_reminder' }),
  );
});
it('uses saved event preview for league-only staff and clears results on channel edits', async () => {
  mount({
    scope: { kind: 'event', eventId: 9, guildId: '900000000000000001' },
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0][0]).toBe('/events/9/permission-checks/');
  act(() =>
    form.setValue(
      'discord_confirm_attendance_channel_id',
      '900000000000000008',
    ),
  );
  expect(
    screen.getByTestId('discord-permission-badge-attendance_reminder'),
  ).toHaveTextContent('Checking');
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][1].checks).toContainEqual(
    expect.objectContaining({
      key: 'attendance_reminder',
      channel_id: '900000000000000008',
    }),
  );
});
it('renders pending references, unsupported operations and recipient-dependent DMs separately', async () => {
  post.mockImplementation(async (_path, body) => ({
    data: {
      guild_id: '900000000000000001',
      checks: body.checks.map((d: { key: string; action: string }) => ({
        ...fixture.checks[0],
        ...d,
        status:
          d.key === 'start_mention'
            ? 'unconfigured'
            : d.key === 'mark_interested'
              ? 'unsupported'
              : d.key === 'signup_reminder'
                ? 'not_applicable'
                : 'verified',
        reason: d.key === 'start_mention' ? 'pending_signup_post' : null,
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      })),
    },
  }));
  mount();
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-start_mention'),
    ).toHaveTextContent('Pending signup post'),
  );
  expect(
    screen.getByTestId('discord-permission-badge-mark_interested'),
  ).toHaveTextContent('Unsupported operation');
  expect(
    screen.getByTestId('discord-permission-badge-signup_reminder'),
  ).toHaveTextContent('Recipient dependent');
});
it('does not request without a configured scope and shows no server', () => {
  mount({ scope: null });
  expect(post).not.toHaveBeenCalled();
  expect(
    screen.getByTestId('discord-permission-badge-attendance_reminder'),
  ).toHaveTextContent('No server configured');
});
it('does not request without staff access', () => {
  mount({ canCheck: false });
  expect(post).not.toHaveBeenCalled();
});
it('keeps disabled operations neutral even when their effective permissions verify', async () => {
  post.mockImplementation(async (_path, body) => ({
    data: {
      guild_id: '900000000000000001',
      checks: body.checks.map((d: { key: string; action: string }) => ({
        ...fixture.checks[0],
        ...d,
        status: 'verified',
        checked_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      })),
    },
  }));
  mount();
  await waitFor(() =>
    expect(
      screen.getByTestId('discord-permission-badge-attendance_reminder'),
    ).toHaveTextContent('Permissions verified'),
  );
  act(() => form.setValue('discord_confirm_attendance', false));
  expect(
    screen
      .getByTestId('discord-permission-badge-attendance_reminder')
      .querySelector('[data-slot="badge"]'),
  ).not.toHaveClass('text-success');
});
