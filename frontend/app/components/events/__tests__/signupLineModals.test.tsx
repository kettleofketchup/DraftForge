// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  event,
  openTab,
  orgDefaults,
  repeater,
  submit,
  Wrapper,
} from './eventModalFixtures';

// Write seams of the three edit surfaces; the body is the assertion target.
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

import { EditEventModal } from '../EditEventModal';
import { EditRepeaterModal } from '../EditRepeaterModal';
import { OrgEventDefaultsHarness } from './orgEventDefaultsHarness';

const FIELDS = ['line_withdraw_forfeits', 'line_switch_restamps'] as const;
type Field = (typeof FIELDS)[number];

async function uncheck(name: Field, tab: RegExp) {
  openTab(tab);
  fireEvent.click(await screen.findByTestId(`signup-line-${name}`));
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.mutateAsync.mockResolvedValue({});
  api.getOrgEventDefaults.mockResolvedValue(orgDefaults);
});

describe('EditEventModal signup line', () => {
  it('keeps the saved staff reason policy through reset and submit', async () => {
    render(
      <EditEventModal
        event={{ ...event, staff_reason_policy: 'all_staff_changes' }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    openTab(/approval/i);
    expect(
      await screen.findByTestId('signup-line-staff_reason_policy'),
    ).toHaveTextContent('Required for every staff change');
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      staff_reason_policy: 'all_staff_changes',
    });
  });

  it.each(FIELDS)('sends %s false once unchecked', async (name) => {
    render(<EditEventModal event={event} open onOpenChange={() => {}} />, {
      wrapper: Wrapper,
    });
    await uncheck(name, /approval/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      line_withdraw_forfeits: name !== 'line_withdraw_forfeits',
      line_switch_restamps: name !== 'line_switch_restamps',
    });
  });

  it("starts from the event's rules", async () => {
    render(
      <EditEventModal
        event={{ ...event, line_withdraw_forfeits: false }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    openTab(/approval/i);
    expect(
      await screen.findByTestId('signup-line-line_withdraw_forfeits'),
    ).not.toBeChecked();
    expect(
      screen.getByTestId('signup-line-line_switch_restamps'),
    ).toBeChecked();
  });
});

describe('EditRepeaterModal signup line', () => {
  it('keeps the saved staff reason policy through reset and submit', async () => {
    render(
      <EditRepeaterModal
        repeater={{ ...repeater, staff_reason_policy: 'all_staff_changes' }}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: Wrapper },
    );
    openTab(/^event$/i);
    expect(
      await screen.findByTestId('signup-line-staff_reason_policy'),
    ).toHaveTextContent('Required for every staff change');
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      staff_reason_policy: 'all_staff_changes',
    });
  });

  it.each(FIELDS)('sends %s false once unchecked', async (name) => {
    render(
      <EditRepeaterModal repeater={repeater} open onOpenChange={() => {}} />,
      { wrapper: Wrapper },
    );
    await uncheck(name, /^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      line_withdraw_forfeits: name !== 'line_withdraw_forfeits',
      line_switch_restamps: name !== 'line_switch_restamps',
    });
  });
});

describe('org event defaults signup line', () => {
  async function renderLoaded() {
    render(<OrgEventDefaultsHarness organizationId={1} />, {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(api.getOrgEventDefaults).toHaveBeenCalled());
    expect(
      await screen.findByTestId('org-defaults-max-players-input'),
    ).toHaveValue(orgDefaults.max_players);
  }

  it.each(FIELDS)('sends %s false once unchecked', async (name) => {
    await renderLoaded();
    await uncheck(name, /^event$/i);
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      id: orgDefaults.id,
      data: {
        line_withdraw_forfeits: name !== 'line_withdraw_forfeits',
        line_switch_restamps: name !== 'line_switch_restamps',
      },
    });
  });

  it('keeps the saved staff reason policy through reset and submit', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      staff_reason_policy: 'all_staff_changes',
    });
    await renderLoaded();
    openTab(/^event$/i);
    expect(
      await screen.findByTestId('signup-line-staff_reason_policy'),
    ).toHaveTextContent('Required for every staff change');
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      data: { staff_reason_policy: 'all_staff_changes' },
    });
  });

  it('keeps a saved rule through the reset and sends it back', async () => {
    api.getOrgEventDefaults.mockResolvedValue({
      ...orgDefaults,
      line_switch_restamps: false,
    });
    await renderLoaded();
    openTab(/^event$/i);
    expect(
      await screen.findByTestId('signup-line-line_switch_restamps'),
    ).not.toBeChecked();
    fireEvent.click(screen.getByTestId('signup-rules-allow_user_signups'));
    submit();
    await waitFor(() => expect(api.mutateAsync).toHaveBeenCalled());
    expect(api.mutateAsync.mock.calls[0][0]).toMatchObject({
      data: {
        allow_user_signups: false,
        line_withdraw_forfeits: true,
        line_switch_restamps: false,
      },
    });
  });
});
