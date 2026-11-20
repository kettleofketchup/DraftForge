// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import type { UserType } from '~/components/user/types';
import { createI18nInstance } from '~/i18n/config';
import { useUserStore } from '~/store/userStore';
import type { OrganizationType } from '../schemas';

const updateOrganization = vi.hoisted(() => vi.fn());
const mutateAsync = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
const toastSuccess = vi.hoisted(() => vi.fn());
const toastWarning = vi.hoisted(() => vi.fn());
const staffPlacementEnabled = vi.hoisted(() => vi.fn());

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
  updateOrganization,
  getOrgEventDefaults: vi.fn(async () => defaults),
}));
vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useUpdateOrgDefaultsMutation: () => ({ mutateAsync, isPending: false }),
}));
vi.mock('../tabs/orgSettings/StaffPlacementSection', () => ({
  useStaffPlacementSection: (_id: number, enabled: boolean) => {
    staffPlacementEnabled(enabled);
    return {
      content: <div data-testid="staff-placement-stub" />,
      unit: undefined,
    };
  },
}));
vi.mock('~/components/admin-team', () => ({
  AdminTeamSection: () => <div data-testid="admin-team-section" />,
}));
vi.mock('sonner', () => ({
  toast: { error: toastError, success: toastSuccess, warning: toastWarning },
}));

import * as api from '~/components/api/api';
import { useOrgSettingsParam } from '../hooks/useOrgSettingsParam';
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

const VIEWER = 5;

const ORG = {
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
  admin_ids: [VIEWER],
  staff_ids: [],
  members_viewer_pk: VIEWER,
} as unknown as OrganizationType;

const onOpenChangeSpy = vi.fn();

let setOrgForTest: (org: OrganizationType) => void = () => undefined;

function Harness({
  initialOrganization,
  initialSection = null,
}: {
  initialOrganization: OrganizationType;
  initialSection?: string | null;
}): ReactNode {
  const [organization, setOrganization] = useState(initialOrganization);
  setOrgForTest = setOrganization;
  const [open, setOpen] = useState(true);
  const [section, setSection] = useState<string | null>(initialSection);
  return (
    <>
      <OrgSettingsDialog
        organization={organization}
        open={open}
        section={section}
        onSectionChange={setSection}
        onOpenChange={(next) => {
          onOpenChangeSpy(next);
          setOpen(next);
        }}
      />
      <button
        type="button"
        data-testid="reopen"
        onClick={() => setOpen(true)}
      />
    </>
  );
}

let client: QueryClient;
const i18n = createI18nInstance('en');

function wrap(node: ReactNode, entries = ['/org']) {
  const router = createMemoryRouter([{ path: '*', element: node }], {
    initialEntries: entries,
    initialIndex: entries.length - 1,
  });
  return {
    router,
    ui: (
      <QueryClientProvider client={client}>
        <I18nextProvider i18n={i18n}>
          <TooltipProvider>
            <RouterProvider router={router} />
          </TooltipProvider>
        </I18nextProvider>
      </QueryClientProvider>
    ),
  };
}

function renderDialog(
  initialSection: string | null = null,
  organization: OrganizationType = ORG,
) {
  const utils = render(
    wrap(
      <Harness
        initialOrganization={organization}
        initialSection={initialSection}
      />,
    ).ui,
  );
  return {
    ...utils,
    rerenderWith: (next: OrganizationType) => act(() => setOrgForTest(next)),
  };
}

function UrlHarness(): ReactNode {
  const param = useOrgSettingsParam({ settled: true, canOpen: true });
  const location = useLocation();
  return (
    <>
      <span data-testid="url">{`${location.pathname}${location.search}`}</span>
      {param.open ? (
        <OrgSettingsDialog
          organization={ORG}
          open
          section={param.section}
          onSectionChange={param.setSection}
          onOpenChange={(next) => {
            if (!next) param.close();
          }}
        />
      ) : (
        <div data-testid="closed" />
      )}
    </>
  );
}

function renderUrlDialog() {
  const { router, ui } = wrap(<UrlHarness />, [
    '/org',
    '/org?settings=general',
  ]);
  render(ui);
  return router;
}
const url = () => screen.getByTestId('url').textContent;

const tab = (value: string) => screen.getByTestId(`org-settings-tab-${value}`);
const isActive = (value: string) =>
  tab(value).getAttribute('data-state') === 'active';

async function defaultsLoaded() {
  fireEvent.mouseDown(tab('defaults-event'), { button: 0 });
  await waitFor(() =>
    expect(screen.getByTestId('draft-settings-team-grace-s')).toHaveValue(20),
  );
}

function editBoth() {
  fireEvent.change(screen.getByTestId('org-name-input'), {
    target: { value: 'Renamed' },
  });
  fireEvent.change(screen.getByTestId('org-defaults-max-players-input'), {
    target: { value: '12' },
  });
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useUserStore.setState({
    currentUser: { pk: VIEWER, username: 'viewer' } as UserType,
  });
  updateOrganization.mockReset().mockResolvedValue({});
  mutateAsync.mockReset().mockResolvedValue({});
  toastError.mockReset();
  toastSuccess.mockReset();
  toastWarning.mockReset();
  staffPlacementEnabled.mockReset();
  vi.mocked(api.getOrgEventDefaults).mockClear();
  onOpenChangeSpy.mockReset();
});
afterEach(cleanup);

describe('OrgSettingsDialog', () => {
  it('admin sees both group headings and all eleven sections in order', async () => {
    renderDialog();
    expect(screen.getByTestId('org-settings-modal')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Organization Settings' }),
    ).toBeInTheDocument();
    const sidebar = screen.getByTestId('org-settings-sidebar');
    expect(within(sidebar).getByText('Organization')).toBeInTheDocument();
    expect(within(sidebar).getByText('New Event Defaults')).toBeInTheDocument();
    expect(
      within(sidebar)
        .getAllByRole('tab')
        .map((t) => t.getAttribute('data-testid')),
    ).toEqual([
      'org-settings-tab-general',
      'org-settings-tab-discord',
      'org-settings-tab-members',
      'org-settings-tab-rules',
      'org-settings-tab-admins',
      'org-settings-tab-staff-placement',
      'org-settings-tab-defaults-event',
      'org-settings-tab-defaults-tournament',
      'org-settings-tab-defaults-lobby',
      'org-settings-tab-defaults-discord',
      'org-settings-tab-defaults-ready',
    ]);
    expect(staffPlacementEnabled).not.toHaveBeenCalledWith(true);
    await defaultsLoaded();
  });

  it('saving an invalid field opens and marks its section', async () => {
    renderDialog();
    await defaultsLoaded();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: '' },
    });
    fireEvent.mouseDown(tab('rules'), { button: 0 });
    fireEvent.click(await screen.findByTestId('org-settings-save'));
    await waitFor(() => expect(isActive('general')).toBe(true));
    expect(tab('general')).toHaveAttribute('data-invalid');
    expect(updateOrganization).not.toHaveBeenCalled();
  });

  it('opens on the requested section; an unknown section falls back to general', async () => {
    const first = renderDialog('staff-placement');
    expect(isActive('staff-placement')).toBe(true);
    expect(screen.getByTestId('staff-placement-stub')).toBeVisible();
    await defaultsLoaded();
    first.unmount();

    renderDialog('nope');
    expect(isActive('general')).toBe(true);
    await defaultsLoaded();
  });

  it('save bar appears after an edit and Save calls each dirty endpoint', async () => {
    renderDialog();
    await defaultsLoaded();
    expect(screen.queryByTestId('org-settings-save-bar')).toBeNull();

    editBoth();
    fireEvent.click(await screen.findByTestId('org-settings-save'));

    await waitFor(() =>
      expect(updateOrganization).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ name: 'Renamed' }),
      ),
    );
    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).toMatchObject({
      id: 3,
      data: { max_players: 12 },
    });
    await waitFor(() =>
      expect(screen.queryByTestId('org-settings-save-bar')).toBeNull(),
    );
  });

  it('profile save refetch keeps a dirty event-defaults form dirty', async () => {
    mutateAsync.mockRejectedValue(new Error('boom'));
    const { rerenderWith } = renderDialog();
    await defaultsLoaded();

    editBoth();
    fireEvent.click(await screen.findByTestId('org-settings-save'));
    await waitFor(() => expect(updateOrganization).toHaveBeenCalled());
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith('Failed to update defaults'),
    );
    expect(toastWarning).toHaveBeenCalledTimes(1);

    rerenderWith({ ...ORG, name: 'Renamed' } as OrganizationType);

    expect(screen.getByTestId('org-name-input')).toHaveValue('Renamed');
    expect(screen.getByTestId('org-defaults-max-players-input')).toHaveValue(
      12,
    );
    expect(screen.getByTestId('org-settings-save-bar')).toBeInTheDocument();
  });

  it('closing while dirty asks to discard; Cancel keeps edits; Discard closes', async () => {
    renderDialog();
    await defaultsLoaded();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'Renamed' },
    });
    await screen.findByTestId('org-settings-save-bar');

    fireEvent.click(screen.getByTestId('dialog-close-button'));
    expect(
      await screen.findByText('Discard unsaved changes?'),
    ).toBeInTheDocument();
    expect(onOpenChangeSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('org-settings-discard-cancel'));
    await waitFor(() =>
      expect(screen.queryByText('Discard unsaved changes?')).toBeNull(),
    );
    expect(screen.getByTestId('org-settings-modal')).toBeInTheDocument();
    expect(screen.getByTestId('org-name-input')).toHaveValue('Renamed');

    fireEvent.click(screen.getByTestId('dialog-close-button'));
    fireEvent.click(await screen.findByTestId('org-settings-discard-confirm'));
    await waitFor(() => expect(onOpenChangeSpy).toHaveBeenCalledWith(false));
    await waitFor(() =>
      expect(screen.queryByTestId('org-settings-modal')).toBeNull(),
    );
  });

  it('closing a clean dialog closes without asking', async () => {
    renderDialog();
    await defaultsLoaded();
    fireEvent.click(screen.getByTestId('dialog-close-button'));
    expect(onOpenChangeSpy).toHaveBeenCalledWith(false);
    expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
  });

  it('Admin Team mounts lazily', async () => {
    renderDialog();
    expect(screen.queryByTestId('admin-team-section')).toBeNull();
    fireEvent.mouseDown(tab('admins'), { button: 0 });
    expect(isActive('admins')).toBe(true);
    expect(screen.getByTestId('admin-team-section')).toBeInTheDocument();
    await defaultsLoaded();
  });

  it('renders nothing and fetches no settings for a viewer who is not an org admin', async () => {
    renderDialog(null, {
      ...ORG,
      admin_ids: [],
      staff_ids: [VIEWER],
    } as OrganizationType);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId('org-settings-modal')).toBeNull();
    expect(api.getOrgEventDefaults).not.toHaveBeenCalled();
    expect(staffPlacementEnabled).not.toHaveBeenCalledWith(true);
  });

  it('after a successful save, closing does not prompt and success toasts once', async () => {
    renderDialog();
    await defaultsLoaded();
    editBoth();
    fireEvent.click(await screen.findByTestId('org-settings-save'));
    await waitFor(() =>
      expect(screen.queryByTestId('org-settings-save-bar')).toBeNull(),
    );
    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastSuccess).toHaveBeenCalledWith('Settings saved');

    fireEvent.click(screen.getByTestId('dialog-close-button'));
    expect(onOpenChangeSpy).toHaveBeenCalledWith(false);
    expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
  });

  it('Discard then reopen shows the saved server values', async () => {
    renderDialog();
    await defaultsLoaded();
    editBoth();
    fireEvent.click(screen.getByTestId('dialog-close-button'));
    fireEvent.click(await screen.findByTestId('org-settings-discard-confirm'));
    await waitFor(() =>
      expect(screen.queryByTestId('org-settings-modal')).toBeNull(),
    );

    fireEvent.click(screen.getByTestId('reopen'));
    await defaultsLoaded();
    expect(screen.getByTestId('org-name-input')).toHaveValue('Org');
    expect(screen.getByTestId('org-defaults-max-players-input')).toHaveValue(
      null,
    );
    expect(screen.queryByTestId('org-settings-save-bar')).toBeNull();
    expect(updateOrganization).not.toHaveBeenCalled();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('does not close while a save is in flight', async () => {
    let release: () => void = () => undefined;
    updateOrganization.mockImplementation(
      () => new Promise<object>((resolve) => (release = () => resolve({}))),
    );
    renderDialog();
    await defaultsLoaded();
    fireEvent.change(screen.getByTestId('org-name-input'), {
      target: { value: 'Renamed' },
    });
    fireEvent.click(await screen.findByTestId('org-settings-save'));
    await waitFor(() => expect(updateOrganization).toHaveBeenCalled());

    fireEvent.click(screen.getByTestId('dialog-close-button'));
    expect(onOpenChangeSpy).not.toHaveBeenCalled();
    expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
    expect(screen.getByTestId('org-settings-modal')).toBeInTheDocument();

    release();
    await waitFor(() =>
      expect(screen.queryByTestId('org-settings-save-bar')).toBeNull(),
    );
  });

  describe('lazy loading', () => {
    it('opening on General fetches neither defaults nor staff settings', async () => {
      renderDialog();
      await new Promise((r) => setTimeout(r, 20));
      expect(api.getOrgEventDefaults).not.toHaveBeenCalled();
      expect(staffPlacementEnabled).not.toHaveBeenCalledWith(true);
    });

    it('visiting a defaults section fetches the defaults', async () => {
      renderDialog();
      fireEvent.mouseDown(tab('defaults-event'), { button: 0 });
      await waitFor(() => expect(api.getOrgEventDefaults).toHaveBeenCalled());
      expect(staffPlacementEnabled).not.toHaveBeenCalledWith(true);
    });

    it('visiting staff placement enables its fetch', async () => {
      renderDialog();
      fireEvent.mouseDown(tab('staff-placement'), { button: 0 });
      await waitFor(() =>
        expect(staffPlacementEnabled).toHaveBeenCalledWith(true),
      );
      expect(api.getOrgEventDefaults).not.toHaveBeenCalled();
    });

    it('stays loaded after leaving the section', async () => {
      renderDialog();
      await defaultsLoaded();
      fireEvent.mouseDown(tab('general'), { button: 0 });
      editBoth();
      expect(screen.getByTestId('org-settings-save-bar')).toBeInTheDocument();
      expect(screen.getByTestId('org-defaults-max-players-input')).toHaveValue(
        12,
      );
    });
  });

  describe('history navigation with unsaved edits', () => {
    const dirty = async () => {
      fireEvent.change(await screen.findByTestId('org-name-input'), {
        target: { value: 'Renamed' },
      });
      await screen.findByTestId('org-settings-save-bar');
    };

    it('Back asks to discard; Cancel keeps the modal and edits', async () => {
      const router = renderUrlDialog();
      await dirty();
      await act(() => router.navigate(-1));
      expect(
        await screen.findByText('Discard unsaved changes?'),
      ).toBeInTheDocument();
      expect(url()).toBe('/org?settings=general');

      fireEvent.click(screen.getByTestId('org-settings-discard-cancel'));
      await waitFor(() =>
        expect(screen.queryByText('Discard unsaved changes?')).toBeNull(),
      );
      expect(screen.getByTestId('org-name-input')).toHaveValue('Renamed');
      expect(url()).toBe('/org?settings=general');
    });

    it('Back then Discard leaves the page', async () => {
      const router = renderUrlDialog();
      await dirty();
      await act(() => router.navigate(-1));
      fireEvent.click(
        await screen.findByTestId('org-settings-discard-confirm'),
      );
      await waitFor(() => expect(screen.getByTestId('closed')).toBeVisible());
      expect(url()).toBe('/org');
    });

    it('changing only the section is not blocked', async () => {
      renderUrlDialog();
      await dirty();
      fireEvent.mouseDown(tab('rules'), { button: 0 });
      await waitFor(() => expect(url()).toBe('/org?settings=rules'));
      expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
      expect(screen.getByTestId('org-name-input')).toHaveValue('Renamed');
    });

    it('closing with the X prompts once and Discard closes without a second prompt', async () => {
      renderUrlDialog();
      await dirty();
      fireEvent.click(screen.getByTestId('dialog-close-button'));
      fireEvent.click(
        await screen.findByTestId('org-settings-discard-confirm'),
      );
      await waitFor(() => expect(screen.getByTestId('closed')).toBeVisible());
      expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
      expect(url()).toBe('/org');
    });

    it('Back with no edits is not blocked', async () => {
      const router = renderUrlDialog();
      await screen.findByTestId('org-name-input');
      await act(() => router.navigate(-1));
      expect(screen.getByTestId('closed')).toBeVisible();
      expect(screen.queryByText('Discard unsaved changes?')).toBeNull();
    });
  });
});
