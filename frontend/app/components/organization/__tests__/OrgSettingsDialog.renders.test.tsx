// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { createElement, useState, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { createI18nInstance } from '~/i18n/config';
import { useUserStore } from '~/store/userStore';
import type { OrganizationType } from '../schemas';

const api = vi.hoisted(() => ({
  updateOrganization: vi.fn(),
  patchOrgSettings: vi.fn(),
  mutateAsync: vi.fn(),
}));

const org = vi.hoisted(() => ({
  pk: 7,
  name: 'Org',
  description: '',
  logo: '',
  discord_link: '',
  discord_server_id: '',
  rules_template: '',
  timezone: 'America/New_York',
  members_private: false,
  owner_id: 1,
  admin_ids: [5],
  staff_ids: [],
  members_viewer_pk: 5,
  can_manage_conduct: true,
}));

const conductValues = vi.hoisted(() => ({
  late_cancel_hours: 2,
  late_cancel_weight: 0.5,
  half_life_days: 90,
  max_age_days: 365,
  prior_show_rate: 0.85,
  prior_strength: 3,
  min_events: 3,
  leaderboard_public: true,
  back_of_line_enabled: false,
  back_of_line_below: 0.75,
  require_approval_enabled: false,
  require_approval_below: 0.65,
  block_enabled: false,
  block_below: 0.4,
  enforce_on_new_members: false,
}));

const defaults = vi.hoisted(() => ({
  id: 3,
  organization: 7,
  tournament_name: 'Weekly Cup',
  tournament_type: 'double_elimination',
  game_type: 1,
  draft_type: 'shuffle',
  people_per_team: 5,
  number_of_teams: null,
  timezone: 'America/New_York',
  game_mode: 'normal',
  max_players: null,
  auto_approve: false,
  auto_confirm: false,
  discord_create_event: false,
  discord_sync_signups: false,
  discord_event_title: '',
  discord_event_description: '',
  discord_event_info: '',
  discord_signup_reminder: false,
  discord_signup_reminder_hours: 24,
  discord_confirm_attendance: false,
  discord_confirm_attendance_hours: 2,
  discord_profile_reminder: false,
  discord_profile_reminder_hours: 24,
  discord_mark_interested: false,
  discord_post_signups: false,
  discord_post_signups_channel_id: '',
  discord_announcement: false,
  discord_announcement_channel_id: '',
  discord_announcement_hours: 24,
  discord_announcement_role_ids: [],
  discord_signup_role_ids: [],
  discord_start_mention: false,
  discord_start_mention_minutes: 30,
  discord_start_mention_scope: 'main',
  draft_timer_enabled: true,
  draft_grace_time_ms: 20000,
  draft_reserve_time_ms: 40000,
  draft_timeout_action: 'skip_turn',
  hero_timer_enabled: true,
  hero_grace_time_ms: 25000,
  hero_reserve_time_ms: 60000,
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  updateOrganization: api.updateOrganization,
  fetchOrganization: vi.fn(async () => org),
  getOrgEventDefaults: vi.fn(async () => defaults),
}));
vi.mock('~/components/api/orgSettingsAPI', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/orgSettingsAPI')>()),
  getOrgSettings: vi.fn(async () => ({
    organization: 7,
    staff_override_policy: 'silent',
    staff_override_warning_codes: ['over_capacity'],
    available_warning_codes: [{ code: 'over_capacity', label: 'Over' }],
    updated_at: '2026-11-17T12:00:00Z',
  })),
  patchOrgSettings: api.patchOrgSettings,
}));
vi.mock('~/features/conduct/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/features/conduct/api')>()),
  getConductSettings: vi.fn(async () => ({
    ...conductValues,
    defaults: conductValues,
  })),
}));
vi.mock('~/features/discord-connect/api', () => ({
  getDiscordBotStatus: vi.fn().mockResolvedValue({
    has_bot: false,
    reason: 'no_server_configured',
    guild_name: null,
  }),
  getDiscordInstallLink: vi.fn(),
}));
vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useUpdateOrgDefaultsMutation: () => ({ mutateAsync: api.mutateAsync }),
}));
vi.mock('~/components/admin-team', () => ({
  AdminTeamSection: () => {
    renders.admins = (renders.admins ?? 0) + 1;
    return null;
  },
}));
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

// Every field label re-renders with its section, so labels stand in for sections.
const renders = vi.hoisted(() => ({}) as Record<string, number>);
vi.mock('~/components/ui/form', async (importOriginal) => {
  const m = await importOriginal<typeof import('~/components/ui/form')>();
  const FormLabel = (props: Parameters<typeof m.FormLabel>[0]) => {
    const key = String(props.children);
    renders[key] = (renders[key] ?? 0) + 1;
    return createElement(m.FormLabel, props);
  };
  return { ...m, FormLabel };
});

import { OrgSettingsDialog } from '../OrgSettingsDialog';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??=
  ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => undefined;
Element.prototype.scrollIntoView ??= () => undefined;

function Harness(): ReactNode {
  const [section, setSection] = useState<string | null>(null);
  return (
    <OrgSettingsDialog
      organization={org as unknown as OrganizationType}
      open
      section={section}
      onSectionChange={setSection}
      onOpenChange={() => {}}
    />
  );
}

/** Labels rendered since the last call, sorted. */
function rendered(): string[] {
  const keys = Object.keys(renders).sort();
  for (const key of keys) delete renders[key];
  return keys;
}

const tab = (value: string) => screen.getByTestId(`org-settings-tab-${value}`);
const openTab = (value: string) =>
  fireEvent.mouseDown(tab(value), { button: 0 });
const byId = (id: string) => screen.getByTestId(id);
const type = (id: string, value: string) =>
  fireEvent.change(byId(id), { target: { value } });

function chooseOption(trigger: HTMLElement, name: string | RegExp) {
  fireEvent.pointerDown(trigger, {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
  fireEvent.click(screen.getByRole('option', { name }));
}

/** Opens the dialog with every section loaded, back on General. */
async function renderDialog() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter([{ path: '*', element: <Harness /> }], {
    initialEntries: ['/org'],
  });
  render(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={createI18nInstance('en')}>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </I18nextProvider>
    </QueryClientProvider>,
  );
  await screen.findByTestId('org-name-input');
  for (const section of ['admins', 'staff-placement', 'conduct']) {
    openTab(section);
  }
  await screen.findByTestId('org-settings-policy-select');
  await screen.findByText('Prior show rate');
  openTab('defaults-event');
  await screen.findByTestId('org-defaults-max-players-input');
  openTab('general');
  rendered();
}

async function savedPayloads(edit: () => void) {
  Object.values(api).forEach((fn) => fn.mockReset().mockResolvedValue({}));
  api.patchOrgSettings.mockResolvedValue({
    organization: 7,
    staff_override_policy: 'confirm',
    staff_override_warning_codes: ['over_capacity'],
    available_warning_codes: [{ code: 'over_capacity', label: 'Over' }],
    updated_at: '2026-11-17T12:00:00Z',
  });
  await renderDialog();
  edit();
  fireEvent.click(await screen.findByTestId('org-settings-save'));
  await waitFor(() =>
    expect(screen.queryByTestId('org-settings-save-bar')).toBeNull(),
  );
  cleanup();
  return {
    profile: api.updateOrganization.mock.calls[0]?.[1],
    staff: api.patchOrgSettings.mock.calls[0]?.[1],
    defaults: api.mutateAsync.mock.calls[0]?.[0],
  };
}

beforeEach(() => {
  useUserStore.setState({
    currentUser: { pk: 5, username: 'viewer' } as UserType,
  });
  rendered();
});

describe('OrgSettingsDialog renders', () => {
  it('an edit re-renders only its own field, not the other sections', async () => {
    await renderDialog();

    for (const value of ['O', 'Or', 'Org!']) type('org-name-input', value);
    expect(rendered()).toEqual(['Organization Name']);

    fireEvent.click(byId('org-members-private-switch'));
    fireEvent.click(byId('org-members-private-switch'));
    expect(rendered()).toEqual(['Private members list']);

    fireEvent.click(byId('org-defaults-auto-approve-checkbox'));
    fireEvent.click(byId('signup-rules-allow_user_signups'));
    expect(rendered()).toEqual([
      'Auto-approve signups',
      'Members can sign themselves up',
    ]);

    type('org-defaults-max-players-input', '12');
    expect(rendered()).toEqual(['Max Players']);

    chooseOption(byId('org-settings-policy-select'), /confirm/i);
    expect(rendered()).toEqual(['Staff override policy']);
  });

  it('after a failed save, edits still re-render only their own field', async () => {
    await renderDialog();
    type('org-name-input', '');
    fireEvent.click(await screen.findByTestId('org-settings-save'));
    await waitFor(() => expect(tab('general')).toHaveAttribute('data-invalid'));
    rendered();

    type('org-description-input', 'a');
    type('org-description-input', 'ab');
    fireEvent.click(byId('org-members-private-switch'));
    expect(rendered()).toEqual(['Description', 'Private members list']);

    type('org-name-input', 'N');
    await waitFor(() =>
      expect(tab('general')).not.toHaveAttribute('data-invalid'),
    );
    expect(rendered()).toEqual(['Organization Name']);
  });

  it('saves each edited form with only its edits, across tab switches', async () => {
    const untouched = await savedPayloads(() => {
      type('org-name-input', 'Renamed');
      type('org-defaults-max-players-input', '12');
    });

    const edited = await savedPayloads(() => {
      type('org-name-input', 'Renamed');
      openTab('members');
      fireEvent.click(byId('org-members-private-switch'));
      openTab('defaults-event');
      type('org-defaults-max-players-input', '12');
      fireEvent.click(byId('org-defaults-auto-approve-checkbox'));
      openTab('staff-placement');
      chooseOption(byId('org-settings-policy-select'), /confirm/i);
      openTab('general');
      openTab('defaults-event');

      expect(byId('org-name-input')).toHaveValue('Renamed');
      expect(byId('org-members-private-switch')).toBeChecked();
      expect(byId('org-defaults-max-players-input')).toHaveValue(12);
      expect(byId('org-defaults-auto-approve-checkbox')).toBeChecked();
    });

    expect(untouched.staff).toBeUndefined();
    expect(edited.profile).toEqual({
      ...untouched.profile,
      members_private: true,
    });
    expect(edited.staff).toEqual({ staff_override_policy: 'confirm' });
    expect(edited.defaults).toEqual({
      ...untouched.defaults,
      data: { ...untouched.defaults.data, auto_approve: true },
    });
  });
});
