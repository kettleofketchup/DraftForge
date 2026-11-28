// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DiscordPermissionBadge, badgeView } from '../DiscordPermissionBadge';
import { RecheckPermissionsButton } from '../RecheckPermissionsButton';
import type { PermissionCheckResult } from '../schemas';

const now = new Date('2026-11-26T12:00:00Z');
function result(
  overrides: Partial<PermissionCheckResult> = {},
): PermissionCheckResult {
  return {
    key: 'announcement',
    action: 'announcement',
    status: 'verified',
    destination: {
      kind: 'channel',
      channel_id: '900000000000000001',
      parent_id: null,
      name: 'event-updates',
      channel_type: 0,
      source: 'configured',
    },
    required_all: ['VIEW_CHANNEL', 'SEND_MESSAGES', 'EMBED_LINKS'],
    required_any: [],
    missing: [],
    granted: ['VIEW_CHANNEL', 'SEND_MESSAGES', 'EMBED_LINKS'],
    effective_permissions: '19456',
    raw_permissions: '19456',
    base_granted: ['VIEW_CHANNEL', 'SEND_MESSAGES', 'EMBED_LINKS'],
    bypass: null,
    blockers: [],
    reason: null,
    checked_at: '2026-11-26T11:59:50Z',
    expires_at: '2099-11-26T12:00:50Z',
    retry_after_seconds: null,
    refresh_state: 'cached',
    ...overrides,
  };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
describe('badgeView', () => {
  it.each([
    ['verified', null, 'success', 'Permissions verified'],
    ['missing_permissions', null, 'error', 'Missing permissions'],
    ['unknown', 'network_error', 'neutral', 'Unable to verify'],
    ['unconfigured', 'no_channel_configured', 'neutral', 'No channel'],
    ['unconfigured', 'no_server_configured', 'neutral', 'No server configured'],
    ['unconfigured', 'pending_signup_post', 'neutral', 'Pending signup post'],
    ['unconfigured', null, 'neutral', 'Not configured'],
    [
      'unsupported',
      'unsupported_channel_type',
      'warning',
      'Cannot verify operation',
    ],
    ['not_applicable', null, 'neutral', 'Recipient dependent'],
  ] as const)('%s / %s', (status, reason, tone, label) => {
    expect(
      badgeView(result({ status, reason }), 'ready', now, false),
    ).toMatchObject({ tone, label });
  });
  it('distinguishes unsupported endpoints', () => {
    expect(
      badgeView(
        result({ status: 'unsupported', action: 'mark_interested' }),
        'ready',
        now,
        false,
      ).label,
    ).toBe('Unsupported operation');
  });
  it('never shows stale, disabled, loading or failed checks as success', () => {
    expect(
      badgeView(result({ expires_at: now.toISOString() }), 'ready', now, false),
    ).toMatchObject({ tone: 'neutral', label: 'Check expired' });
    expect(
      badgeView(result({ expired: true }), 'ready', now, false).label,
    ).toBe('Check expired');
    expect(badgeView(result(), 'ready', now, true).tone).toBe('neutral');
    expect(badgeView(result(), 'checking', now, false)).toMatchObject({
      tone: 'neutral',
      label: 'Checking…',
    });
    expect(badgeView(result(), 'error', now, false)).toMatchObject({
      tone: 'neutral',
      label: 'Unable to verify',
    });
    expect(badgeView(undefined, 'idle', now, false)).toMatchObject({
      tone: 'neutral',
      label: 'Not checked',
    });
    expect(
      badgeView(result({ expires_at: null }), 'ready', now, false).tone,
    ).toBe('neutral');
  });
  it.each([
    'verified',
    'missing_permissions',
    'unknown',
    'unconfigured',
    'unsupported',
    'not_applicable',
  ] as const)('disabled %s is neutral', (status) => {
    expect(badgeView(result({ status }), 'ready', now, true).tone).toBe(
      'neutral',
    );
  });
});
it('has an operation and destination name and does not submit a surrounding form', () => {
  const submit = vi.fn();
  render(
    <form onSubmit={submit}>
      <DiscordPermissionBadge
        operationLabel="Announcement"
        result={result()}
        state="ready"
      />
    </form>,
  );
  const trigger = screen.getByRole('button', {
    name: 'Discord Announcement: Permissions verified in #event-updates',
  });
  expect(trigger.getAttribute('type')).toBe('button');
  fireEvent.click(trigger);
  expect(submit).not.toHaveBeenCalled();
  expect(screen.getByRole('dialog')).toBeTruthy();
});
it('opens permission details with keyboard activation', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Announcement"
      result={result()}
      state="ready"
    />,
  );
  const trigger = screen.getByRole('button');
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'Enter', code: 'Enter' });
  // jsdom does not synthesize the native button click for Enter.
  fireEvent.click(trigger, { detail: 0 });
  expect(screen.getByRole('dialog')).toBeTruthy();
});
it('separates missing alternatives, blockers and collapsible effective grants', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Update event"
      state="ready"
      result={result({
        action: 'scheduled_event_update',
        status: 'missing_permissions',
        missing: ['EMBED_LINKS', 'CREATE_EVENTS', 'MANAGE_EVENTS'],
        required_any: [['CREATE_EVENTS', 'MANAGE_EVENTS']],
        granted: ['VIEW_CHANNEL'],
        base_granted: ['VIEW_CHANNEL', 'CREATE_EVENTS'],
        blockers: [
          {
            code: 'role_not_mentionable',
            detail: null,
            role_id: '900000000000000002',
            missing: [],
          },
        ],
      })}
    />,
  );
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByText('Embed Links')).toBeTruthy();
  expect(screen.getByText('Create Events or Manage Events')).toBeTruthy();
  expect(screen.getByText('Blockers')).toBeTruthy();
  expect(screen.getByText(/make this role mentionable/i)).toBeTruthy();
  const grants = screen.getByText('Granted permissions').closest('details');
  expect(grants?.hasAttribute('open')).toBe(false);
  expect(screen.getByText('Before timeout')).toBeTruthy();
  expect(screen.getByText(/UTC/)).toBeTruthy();
  expect(screen.getByText(/does not guarantee delivery/)).toBeTruthy();
  expect(screen.queryByText(/administrator/i)).toBeNull();
});
it('labels expired grant details as historical and never recommends a bypass', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Announcement"
      state="ready"
      result={result({
        expired: true,
        granted: ['ADMINISTRATOR', 'VIEW_CHANNEL'],
      })}
    />,
  );
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByText('Previously observed permissions')).toBeTruthy();
  expect(screen.queryByText(/administrator/i)).toBeNull();
});
it('does not expose old grants while checking or after a failed request', () => {
  const view = render(
    <DiscordPermissionBadge
      operationLabel="Announcement"
      state="checking"
      result={result()}
    />,
  );
  fireEvent.click(screen.getByRole('button'));
  expect(screen.queryByText('Granted permissions')).toBeNull();
  view.rerender(
    <DiscordPermissionBadge
      operationLabel="Announcement"
      state="error"
      result={result()}
    />,
  );
  expect(screen.queryByText('Granted permissions')).toBeNull();
});
it('does not present unverified alternatives as known missing permissions', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Update event"
      state="ready"
      result={result({
        status: 'unknown',
        reason: 'network_error',
        granted: null,
        required_any: [['CREATE_EVENTS', 'MANAGE_EVENTS']],
      })}
    />,
  );
  fireEvent.click(screen.getByRole('button'));
  expect(
    screen.queryByRole('region', { name: 'Missing permissions' }),
  ).toBeNull();
  expect(screen.queryByText(/Allow Create Events/)).toBeNull();
});
it('uses a non-submitting batch recheck button and disables duplicate requests', () => {
  const onRecheck = vi.fn().mockResolvedValue(undefined);
  const submit = vi.fn();
  const view = render(
    <form onSubmit={submit}>
      <RecheckPermissionsButton onRecheck={onRecheck} isRechecking={false} />
    </form>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Recheck permissions' }));
  expect(onRecheck).toHaveBeenCalledTimes(1);
  expect(submit).not.toHaveBeenCalled();
  view.rerender(
    <RecheckPermissionsButton onRecheck={onRecheck} isRechecking />,
  );
  expect(screen.getByRole('button').hasAttribute('disabled')).toBe(true);
});

function mountBadge() {
  render(
    <DiscordPermissionBadge
      operationLabel="Announcement"
      result={result()}
      state="ready"
    />,
  );
  return screen.getByRole('button');
}
it('renders only the compact badge as its native popover button', () => {
  const trigger = mountBadge();
  expect(trigger.tagName).toBe('BUTTON');
  expect(trigger).toHaveAttribute('type', 'button');
  expect(trigger).toHaveClass('px-2', 'py-0.5', 'text-success');
  expect(trigger.className).not.toMatch(/gradient|shadow-lg|min-h-11/);
  expect(trigger.querySelector('[data-slot="badge"]')).toBeNull();
  expect(trigger).toHaveAttribute('aria-expanded', 'false');
});
it('opens on hover, lets the pointer cross into details, and closes after leaving', () => {
  vi.useFakeTimers();
  const trigger = mountBadge();
  fireEvent.pointerEnter(trigger, { pointerType: 'mouse' });
  const panel = screen.getByRole('dialog');
  expect(trigger).toHaveAttribute('aria-expanded', 'true');
  expect(document.activeElement).not.toBe(panel);
  fireEvent.pointerLeave(trigger, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(100));
  fireEvent.pointerEnter(panel, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(250));
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  fireEvent.pointerLeave(panel, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(250));
  expect(screen.queryByRole('dialog')).toBeNull();
  vi.useRealTimers();
});
it('pins a hovered panel with one click and toggles it closed with the next', () => {
  vi.useFakeTimers();
  const trigger = mountBadge();
  fireEvent.pointerEnter(trigger);
  fireEvent.click(trigger);
  fireEvent.pointerLeave(trigger);
  act(() => vi.advanceTimersByTime(250));
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  fireEvent.click(trigger);
  expect(screen.queryByRole('dialog')).toBeNull();
  vi.useRealTimers();
});
it('opens on focus and supports Escape and subsequent keyboard activation', async () => {
  const trigger = mountBadge();
  fireEvent.focus(trigger);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.keyDown(trigger, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  fireEvent.click(trigger, { detail: 0 });
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.keyDown(trigger, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});
it('ignores touch hover, opens on tap and dismisses on outside interaction', async () => {
  const trigger = mountBadge();
  fireEvent(
    trigger,
    Object.assign(new MouseEvent('pointerover', { bubbles: true }), {
      pointerType: 'touch',
    }),
  );
  expect(screen.queryByRole('dialog')).toBeNull();
  fireEvent.click(trigger);
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  await act(async () => {});
  fireEvent.pointerDown(document.body);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
});

it('identifies Discord and exposes one decorative Info affordance', () => {
  const trigger = mountBadge();
  expect(
    trigger.querySelector('[data-testid="discord-permission-discord-icon"]'),
  ).toHaveAttribute('aria-hidden', 'true');
  expect(
    trigger.querySelector('[data-testid="discord-permission-info-icon"]'),
  ).toHaveAttribute('aria-hidden', 'true');
  expect(screen.getAllByRole('button')).toHaveLength(1);
});
it.each([
  'missing_permissions',
  'unknown',
  'unconfigured',
  'unsupported',
] as const)(
  'does not hide a %s fallback behind a verified primary',
  (status) => {
    render(
      <DiscordPermissionBadge
        operationLabel="Signup post"
        result={result()}
        checks={[
          {
            operationLabel: 'Primary signup',
            result: result({ key: 'signup_post' }),
          },
          {
            operationLabel: 'Announcement fallback',
            result: result({ key: 'signup_fallback', status }),
          },
        ]}
        state="ready"
      />,
    );
    const trigger = screen.getByRole('button');
    expect(trigger).not.toHaveClass('text-success');
    fireEvent.click(trigger);
    expect(
      screen.getByRole('heading', { name: 'Primary signup permissions' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', {
        name: 'Announcement fallback permissions',
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  },
);
it('keeps a grouped expired or disabled result neutral', () => {
  const checks = [
    { operationLabel: 'Primary signup', result: result() },
    {
      operationLabel: 'Announcement fallback',
      result: result({ expired: true }),
    },
  ];
  const view = render(
    <DiscordPermissionBadge
      operationLabel="Signup post"
      result={result()}
      checks={checks}
      state="ready"
    />,
  );
  expect(screen.getByRole('button')).toHaveTextContent('Check expired');
  expect(screen.getByRole('button')).not.toHaveClass('text-success');
  view.rerender(
    <DiscordPermissionBadge
      operationLabel="Signup post"
      result={result()}
      checks={[checks[0]]}
      state="ready"
      disabled
    />,
  );
  expect(screen.getByRole('button')).not.toHaveClass('text-success');
});
it('explains which settings work, are blocked, or cannot be verified', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Announcement channel"
      channel
      result={undefined}
      state="ready"
      checks={[
        {
          operationLabel: 'Pre-day announcement',
          result: result({
            status: 'missing_permissions',
            missing: ['EMBED_LINKS'],
          }),
        },
        {
          operationLabel: 'Post new events',
          result: result({ key: 'new_event_notice' }),
        },
        {
          operationLabel: 'Post attendance reminder in Discord',
          result: result({ key: 'attendance_reminder', status: 'unknown' }),
        },
      ]}
    />,
  );
  const trigger = screen.getByRole('button');
  expect(trigger).toHaveTextContent('1 setting blocked');
  expect(trigger).not.toHaveClass('text-success');
  fireEvent.click(trigger);
  for (const name of ['Working', 'Blocked', 'Unable to verify'])
    expect(screen.getByRole('heading', { name })).toBeInTheDocument();
  expect(
    screen.getByText(
      "Pre-day announcement won't post here — missing Embed Links.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText('Post new events can post here.'),
  ).toBeInTheDocument();
  expect(screen.getAllByText('Required permissions')).toHaveLength(3);
});
it.each([
  undefined,
  result({ expired: true }),
  result({ status: 'unknown' }),
  result({ status: 'unsupported' }),
  result({ status: 'unconfigured' }),
])('never makes a channel green with an unverified use: %j', (unverified) => {
  render(
    <DiscordPermissionBadge
      operationLabel="Channel"
      channel
      result={undefined}
      state="ready"
      checks={[
        { operationLabel: 'Signup', result: result() },
        { operationLabel: 'Other setting', result: unverified },
      ]}
    />,
  );
  expect(screen.getByRole('button')).not.toHaveClass('text-success');
});
it('counts a setting with two blocked uses once', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Channel"
      channel
      result={undefined}
      state="ready"
      checks={[
        {
          operationLabel: 'Post event signup embed',
          settingLabel: 'Post event signup embed',
          result: result({ status: 'missing_permissions' }),
        },
        {
          operationLabel: 'Post event signup embed (announcement fallback)',
          settingLabel: 'Post event signup embed',
          result: result({
            key: 'signup_fallback',
            status: 'missing_permissions',
          }),
        },
      ]}
    />,
  );
  expect(screen.getByRole('button')).toHaveTextContent('1 setting blocked');
});
it('keeps a channel with no enabled uses neutral', () => {
  render(
    <DiscordPermissionBadge
      operationLabel="Channel"
      channel
      result={undefined}
      checks={[]}
      state="ready"
    />,
  );
  expect(screen.getByRole('button')).toHaveTextContent('No enabled settings');
  expect(screen.getByRole('button')).not.toHaveClass('text-success');
});
it('bounds and focuses its scrollable details within available viewport space', () => {
  fireEvent.click(mountBadge());
  const panel = screen.getByRole('dialog');
  expect(panel.className).toContain('--radix-popover-content-available-height');
  expect(panel).toHaveClass('overflow-hidden');
  const title = screen.getByTestId('discord-permission-details-title');
  const scroll = screen.getByTestId('discord-permission-details-scroll');
  expect(title).toHaveTextContent('Announcement permissions');
  expect(scroll).not.toContainElement(title);
  expect(scroll).toHaveClass('overscroll-contain', 'touch-pan-y');
  expect(scroll).toHaveAttribute('tabindex', '0');
  expect(scroll).toHaveFocus();
});

it('keeps the details portal inside an enclosing dialog scroll lock', () => {
  render(
    <div role="dialog" aria-label="Settings">
      <DiscordPermissionBadge
        operationLabel="Announcement"
        result={result()}
        state="ready"
      />
    </div>,
  );
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByRole('dialog', { name: 'Settings' })).toContainElement(
    screen.getByRole('dialog', { name: 'Announcement permission details' }),
  );
});

it('restores the badge on Escape even when touch scrolling has blurred the panel', async () => {
  const trigger = mountBadge();
  fireEvent.click(trigger);
  const panel = screen.getByRole('dialog');
  fireEvent.blur(panel, { relatedTarget: null });
  fireEvent.keyDown(panel, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(trigger).toHaveFocus();
});
