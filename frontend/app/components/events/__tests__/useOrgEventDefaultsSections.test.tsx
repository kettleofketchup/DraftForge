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
import { StrictMode, type ReactNode, type RefObject } from 'react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SettingsDialogHandle } from '~/components/patterns/SettingsDialog';
import type { SettingsFormUnit } from '~/components/patterns/settingsSaveBar';
import { TooltipProvider } from '~/components/ui/tooltip';
import { createI18nInstance } from '~/i18n/config';
import { READY_CHECK_TEST_IDS as IDS } from '../form/testIds';

const mutateAsync = vi.fn().mockResolvedValue({});
vi.mock('~/hooks/useEvent', () => ({
  useUpdateOrgDefaultsMutation: () => ({ mutateAsync, isPending: false }),
}));

const defaults = vi.hoisted(() => ({
  id: 3,
  organization: 1,
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
  discord_announcement_role_ids: ['111', '112'],
  discord_signup_role_ids: ['222'],
  discord_start_mention: true,
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
  getOrgEventDefaults: vi.fn().mockResolvedValue(defaults),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { toast } from 'sonner';
import * as api from '~/components/api/api';
import { useOrgEventDefaultsSections } from '../useOrgEventDefaultsSections';

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

let client: QueryClient;

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={createI18nInstance('en')}>
        <TooltipProvider>{children}</TooltipProvider>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

const selectSection = vi.fn();
const sectionsRef = {
  current: { selectSection, sectionOfField: () => undefined },
} as unknown as RefObject<SettingsDialogHandle<string> | null>;

let unit: SettingsFormUnit;
let sectionValues: { value: string; group?: string }[] = [];

function Harness(): ReactNode {
  const { sections, unit: u } = useOrgEventDefaultsSections(
    1,
    sectionsRef,
    true,
  );
  unit = u;
  sectionValues = sections;
  return (
    <form>
      {sections.map((s) => (
        <section key={s.value} data-section={s.value}>
          {s.content}
        </section>
      ))}
    </form>
  );
}

function renderHarness() {
  return render(
    <StrictMode>
      <Harness />
    </StrictMode>,
    { wrapper: Wrapper },
  );
}

async function ready() {
  await waitFor(() =>
    expect(screen.getByTestId('draft-settings-team-grace-s')).toHaveValue(20),
  );
}

async function save(): Promise<boolean> {
  let ok = false;
  await act(async () => {
    ok = await unit.save();
  });
  return ok;
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mutateAsync.mockReset().mockResolvedValue({});
  selectSection.mockReset();
  vi.mocked(toast.error).mockReset();
});
afterEach(cleanup);

describe('useOrgEventDefaultsSections sections', () => {
  it('sections are grouped under New Event Defaults with defaults-* values', async () => {
    renderHarness();
    await ready();
    expect(sectionValues.map((s) => s.value)).toEqual([
      'defaults-event',
      'defaults-tournament',
      'defaults-lobby',
      'defaults-discord',
      'defaults-ready',
    ]);
    expect(new Set(sectionValues.map((s) => s.group))).toEqual(
      new Set(['New Event Defaults']),
    );
  });

  it('renders skeletons until the defaults load', () => {
    vi.mocked(api.getOrgEventDefaults).mockReturnValueOnce(
      new Promise(() => undefined),
    );
    renderHarness();
    expect(screen.queryByTestId('draft-settings-team-grace-s')).toBeNull();
  });
});

describe('useOrgEventDefaultsSections draft settings', () => {
  it('shows saved default timers and sends edits as flat ms fields', async () => {
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    expect(await save()).toBe(true);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    const { id, data } = mutateAsync.mock.calls[0][0];
    expect(id).toBe(3);
    expect(data).toMatchObject({
      draft_timer_enabled: true,
      draft_grace_time_ms: 20000,
      draft_reserve_time_ms: 40000,
      draft_timeout_action: 'skip_turn',
      hero_timer_enabled: false,
      hero_grace_time_ms: 25000,
      hero_reserve_time_ms: 60000,
    });
    expect(data).not.toHaveProperty('draft_grace_time_s');
    expect(data).not.toHaveProperty('hero_reserve_time_s');
  });
});

describe('useOrgEventDefaultsSections ready check', () => {
  it('moves auto-confirm into the Ready check section and saves its keys', async () => {
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId(IDS.autoConfirm));
    await save();

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].data).toMatchObject({
      auto_confirm: true,
      roll_call_enabled: false,
      roll_call_mode: 'manual',
      ready_check_open_minutes: 120,
      ready_check_chase_minutes: 30,
      event_voice_channel_id: '',
    });
  });

  it('turns auto-confirm off when the toggle is turned on', async () => {
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId(IDS.autoConfirm));
    fireEvent.click(screen.getByTestId(IDS.toggle));
    expect(screen.getByTestId(IDS.autoConfirm)).toBeDisabled();
    await save();

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].data).toMatchObject({
      auto_confirm: false,
      roll_call_enabled: true,
      roll_call_mode: 'automatic',
    });
  });

  it('save resolves false and selects defaults-ready for an invalid ready-check value', async () => {
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId(IDS.toggle));
    fireEvent.click(screen.getByTestId(IDS.settingsTrigger));
    fireEvent.change(await screen.findByTestId(IDS.close), {
      target: { value: '999' },
    });

    expect(await save()).toBe(false);
    expect(mutateAsync).not.toHaveBeenCalled();
    expect(selectSection).toHaveBeenCalledWith('defaults-ready');
    expect(toast.error).toHaveBeenCalledWith(
      'Please fix the highlighted fields',
      expect.anything(),
    );
  });
});

describe('useOrgEventDefaultsSections scoping and load errors', () => {
  it('resolves invalid fields within its own sections only', async () => {
    const original = sectionsRef.current;
    const lookup = vi.fn((_field: string, within?: readonly string[]) =>
      within ? within[0] : 'general',
    );
    (sectionsRef as { current: unknown }).current = {
      selectSection,
      sectionOfField: lookup,
    };
    try {
      renderHarness();
      await ready();
      fireEvent.click(screen.getByTestId(IDS.toggle));
      fireEvent.click(screen.getByTestId(IDS.settingsTrigger));
      fireEvent.change(await screen.findByTestId(IDS.close), {
        target: { value: '999' },
      });
      expect(await save()).toBe(false);
      expect(lookup).toHaveBeenCalledWith(
        expect.any(String),
        sectionValues.map((s) => s.value),
      );
      expect(selectSection).toHaveBeenCalledWith('defaults-event');
      expect(selectSection).not.toHaveBeenCalledWith('general');
    } finally {
      (sectionsRef as { current: unknown }).current = original;
    }
  });

  it('shows the load error instead of a skeleton when the query fails', async () => {
    vi.mocked(api.getOrgEventDefaults).mockRejectedValueOnce(new Error('nope'));
    renderHarness();
    const errors = await screen.findAllByTestId('org-defaults-error');
    expect(errors).toHaveLength(5);
    expect(errors[0]).toHaveTextContent(/nope|Failed to load event defaults/);
  });
});

describe('useOrgEventDefaultsSections discord', () => {
  it('saves the stored start mention and role mentions unchanged', async () => {
    renderHarness();
    await ready();
    await save();

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].data).toMatchObject({
      discord_start_mention: true,
      discord_start_mention_minutes: 30,
      discord_start_mention_scope: 'main',
      discord_announcement_role_ids: ['111', '112'],
      discord_signup_role_ids: ['222'],
    });
  });
});

describe('useOrgEventDefaultsSections direct messages', () => {
  const discordSection = () =>
    document.querySelector<HTMLElement>('[data-section="defaults-discord"]')!;

  it('renders the signup reminder default in the Discord section', async () => {
    renderHarness();
    await ready();
    const section = discordSection();
    expect(
      section.querySelector('[data-field="discord_signup_reminder"]'),
    ).not.toBeNull();
    expect(
      within(section).getByText('Signup reminder DM (default for new series)'),
    ).toBeInTheDocument();
    expect(
      within(section).queryByTestId('discord-direct-messages-series-only'),
    ).toBeNull();
  });

  it('saves per-post channels and the signup reminder default', async () => {
    vi.mocked(api.getOrgEventDefaults).mockResolvedValueOnce({
      ...defaults,
      discord_confirm_attendance_channel_id: '666',
      discord_profile_reminder_channel_id: '777',
    } as unknown as Awaited<ReturnType<typeof api.getOrgEventDefaults>>);
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId('discord-discord_signup_reminder'));
    expect(await save()).toBe(true);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0].data).toMatchObject({
      discord_confirm_attendance_channel_id: '666',
      discord_profile_reminder_channel_id: '777',
      discord_signup_reminder: true,
      discord_signup_reminder_hours: 24,
    });
  });
});

describe('useOrgEventDefaultsSections unit', () => {
  it('resolves false and toasts when the request fails', async () => {
    mutateAsync.mockRejectedValueOnce(new Error('boom'));
    renderHarness();
    await ready();
    expect(await save()).toBe(false);
    expect(toast.error).toHaveBeenCalledWith('Failed to update defaults');
  });

  it('reset on load does not clobber a dirty form', async () => {
    renderHarness();
    await ready();
    fireEvent.click(screen.getByTestId('draft-settings-hero-timer-enabled'));
    expect(unit.isDirty).toBe(true);
    vi.mocked(api.getOrgEventDefaults).mockResolvedValueOnce({
      ...defaults,
      tournament_name: 'Refetched',
    } as unknown as Awaited<ReturnType<typeof api.getOrgEventDefaults>>);
    await act(async () => {
      await client.refetchQueries({ queryKey: ['org-event-defaults', 1] });
    });
    expect(unit.isDirty).toBe(true);
    expect(
      screen.getByTestId('draft-settings-hero-timer-enabled'),
    ).not.toBeChecked();
  });
});

describe('useOrgEventDefaultsSections game mode Select inside a form', () => {
  const trigger = () => screen.getByTestId('org-defaults-game-mode-select');

  function chooseGameMode(label: string) {
    fireEvent.pointerDown(trigger(), {
      button: 0,
      ctrlKey: false,
      pointerType: 'mouse',
    });
    fireEvent.click(screen.getByRole('option', { name: label }));
  }

  function refetched(changes: Partial<typeof defaults>) {
    act(() => {
      client.setQueryData(['org-event-defaults', 1], {
        ...defaults,
        ...changes,
      });
    });
  }

  it('discard after changing the Select restores the saved value and is pristine', async () => {
    renderHarness();
    await ready();
    chooseGameMode('Turbo');
    expect(trigger()).toHaveTextContent('Turbo');
    expect(unit.isDirty).toBe(true);

    act(() => unit.discard());
    await waitFor(() => expect(trigger()).toHaveTextContent('Normal'));
    expect(unit.isDirty).toBe(false);
  });

  it('save then a server-normalised value is shown and not dirty', async () => {
    renderHarness();
    await ready();
    chooseGameMode('Turbo');
    expect(await save()).toBe(true);

    refetched({ game_mode: 'custom' });
    await waitFor(() => expect(trigger()).toHaveTextContent('Custom'));
    expect(unit.isDirty).toBe(false);
  });

  it('an unedited refetch with a new server value is adopted and not dirty', async () => {
    renderHarness();
    await ready();
    refetched({ game_mode: 'captains_mode' });
    await waitFor(() => expect(trigger()).toHaveTextContent("Captain's Mode"));
    expect(unit.isDirty).toBe(false);
  });
});
