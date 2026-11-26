// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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
afterEach(cleanup);
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
    name: 'Announcement: Permissions verified in #event-updates',
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
