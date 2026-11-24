// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { READY_CHECK_TEST_IDS } from '../form/testIds';
import {
  event,
  openTab,
  orgDefaults,
  repeater,
  submit,
  Wrapper,
} from './eventModalFixtures';

// Every write seam the five modals use; the body is the assertion target.
const api = vi.hoisted(() => ({
  createEvent: vi.fn(),
  createEventRepeater: vi.fn(),
  createSeriesOneOffEvent: vi.fn(),
  getOrgEventDefaults: vi.fn(),
  mutateAsync: vi.fn(),
}));

vi.mock('~/components/api/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/components/api/api')>()),
  createEvent: api.createEvent,
  createEventRepeater: api.createEventRepeater,
  createSeriesOneOffEvent: api.createSeriesOneOffEvent,
  getOrgEventDefaults: api.getOrgEventDefaults,
  fetchCurrentUser: vi.fn().mockResolvedValue({}),
  getDiscordChannels: vi.fn().mockResolvedValue([]),
  getDiscordRoles: vi.fn().mockResolvedValue([]),
  getLeagues: vi.fn().mockResolvedValue([]),
}));

vi.mock('~/hooks/useEvent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('~/hooks/useEvent')>()),
  useUpdateEventMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateEventRepeaterMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
  useUpdateOrgDefaultsMutation: () => ({
    mutateAsync: api.mutateAsync,
    isPending: false,
  }),
}));

vi.mock('~/hooks/useLobbyPassword', () => ({
  useEventLobbyPassword: () => ({ data: undefined }),
  useRepeaterLobbyPassword: () => ({ data: undefined }),
  useRegenerateEventLobbyPassword: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock('~/components/league/LeagueCombobox', () => ({
  LeagueCombobox: () => null,
}));

// Heavy fields these tests never use; rendering them timed tests out under load.
vi.mock('../form/sections/EventTournamentFields', () => ({
  EventTournamentFields: () => null,
}));
vi.mock('../form/sections/EventLobbyFields', () => ({
  EventLobbyFields: () => null,
}));
vi.mock('../form/fields/TimezoneField', () => ({ TimezoneField: () => null }));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

import { CreateEventModal } from '../CreateEventModal';
import { CreateSeriesEventModal } from '../CreateSeriesEventModal';
import { EditEventModal } from '../EditEventModal';
import { EditRepeaterModal } from '../EditRepeaterModal';
import { OrgEventDefaultsHarness } from './orgEventDefaultsHarness';

const ROSTER_SWITCH = READY_CHECK_TEST_IDS.toggle;
const SELF_SERVE_BOX = 'signup-rules-allow_user_signups';

async function toggleRules(selfServeTab: RegExp = /approval/i) {
  openTab(/ready check/i);
  fireEvent.click(await screen.findByTestId(ROSTER_SWITCH));
  openTab(selfServeTab);
  fireEvent.click(await screen.findByTestId(SELF_SERVE_BOX));
}

async function expectRules(roster: boolean, selfServe: boolean) {
  openTab(/ready check/i);
  const rosterSwitch = await screen.findByTestId(ROSTER_SWITCH);
  expect(rosterSwitch.getAttribute('aria-checked')).toBe(String(roster));
  openTab(/approval/i);
  const selfServeBox = await screen.findByTestId(SELF_SERVE_BOX);
  if (selfServe) expect(selfServeBox).toBeChecked();
  else expect(selfServeBox).not.toBeChecked();
}

const TOGGLED = { roll_call_enabled: true, allow_user_signups: false };

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createEvent.mockResolvedValue({ id: 99 });
  api.createEventRepeater.mockResolvedValue({ id: 98 });
  api.createSeriesOneOffEvent.mockResolvedValue({ id: 97 });
  api.mutateAsync.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('CreateEventModal signup rules', () => {
  async function renderReady() {
    render(
      <CreateEventModal open onOpenChange={() => {}} organizationId={1} />,
      { wrapper: Wrapper },
    );
    fireEvent.change(await screen.findByTestId('event-name-input'), {
      target: { value: 'Night 5' },
    });
  }

  it('starts from the org defaults', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      roll_call_enabled: true,
      allow_user_signups: false,
    });
    await renderReady();
    await expectRules(true, false);
  });

  it('sends both flags for a single event', async () => {
    await renderReady();
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEvent).toHaveBeenCalled());
    expect(api.createEvent.mock.calls[0][0]).toMatchObject(TOGGLED);
  });

  it('sends both flags for a recurring series', async () => {
    await renderReady();
    fireEvent.click(screen.getByTestId('event-recurring-checkbox'));
    await toggleRules();
    submit();
    await waitFor(() => expect(api.createEventRepeater).toHaveBeenCalled());
    expect(api.createEventRepeater.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('CreateSeriesEventModal signup rules', () => {
  it("starts from the series' flags and sends the toggled values", async () => {
    render(
      <CreateSeriesEventModal
        repeater={{ ...repeater, allow_user_signups: false }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    fireEvent.change(screen.getByTestId('one-off-scheduled-input'), {
      target: { value: '2026-09-30T20:00' },
    });
    await expectRules(false, false);
    openTab(/ready check/i);
    fireEvent.click(await screen.findByTestId(ROSTER_SWITCH));
    submit();
    await waitFor(() => expect(api.createSeriesOneOffEvent).toHaveBeenCalled());
    expect(api.createSeriesOneOffEvent.mock.calls[0][1]).toMatchObject(TOGGLED);
  });
});

describe('EditEventModal signup rules', () => {
  it("starts from the event's flags", async () => {
    render(
      <EditEventModal
        event={{ ...event, roll_call_enabled: true }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    await expectRules(true, true);
  });

  it('sends the toggled flags', async () => {
    render(<EditEventModal event={event} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
    await toggleRules();
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('EditRepeaterModal signup rules', () => {
  it('sends the toggled flags', async () => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await toggleRules(/^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject(TOGGLED);
  });
});

describe('org event defaults signup rules', () => {
  it('sends the toggled flags', async () => {
    render(<OrgEventDefaultsHarness organizationId={1} />, {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(api.getOrgEventDefaults).toHaveBeenCalled());
    expect(
      await screen.findByTestId('org-defaults-max-players-input'),
    ).toHaveValue(orgDefaults.max_players);
    await toggleRules(/^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      id: orgDefaults.id,
      data: TOGGLED,
    });
  });
});
